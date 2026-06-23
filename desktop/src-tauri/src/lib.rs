use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::Manager;

struct BackendState {
    child: Option<Child>,
    port: u16,
}

impl BackendState {
    fn new(port: u16) -> Self {
        Self { child: None, port }
    }

    fn kill_port(&self, port: u16) -> Result<(), String> {
        #[cfg(target_os = "macos")]
        {
            let output = Command::new("lsof")
                .args(["-ti", &format!(":{}", port)])
                .output()
                .map_err(|e| format!("Failed to check port: {e}"))?;

            let pids = String::from_utf8_lossy(&output.stdout);
            for pid in pids.lines() {
                if let Ok(pid) = pid.trim().parse::<u32>() {
                    Command::new("kill")
                        .args(["-9", &pid.to_string()])
                        .output()
                        .map_err(|e| format!("Failed to kill process: {e}"))?;
                }
            }
        }
        #[cfg(target_os = "linux")]
        {
            let output = Command::new("fuser")
                .args(["-k", &format!("{}/tcp", port)])
                .output()
                .map_err(|e| format!("Failed to kill process: {e}"))?;
        }
        #[cfg(target_os = "windows")]
        {
            let output = Command::new("cmd")
                .args(["/C", "for /f \"tokens=5\" %a in ('netstat -aon ^| findstr :{}') do taskkill /f /pid %a", port])
                .output()
                .map_err(|e| format!("Failed to kill process: {e}"))?;
        }
        Ok(())
    }

    fn start(&mut self, resource_dir: Option<&Path>) -> Result<(), String> {
        self.kill_port(self.port)?;
        std::thread::sleep(std::time::Duration::from_millis(500));

        let port_str = self.port.to_string();

        // Finder launches apps with a minimal PATH; set it to find python3
        let path = std::env::var("PATH").unwrap_or_default();
        let safe_path = if cfg!(target_os = "windows") {
            format!("{};{}", path, std::env::var("APPDATA").unwrap_or_default())
        } else {
            format!(
                "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:{}",
                path
            )
        };

        // Locate Python: search common locations, then rely on PATH
        let python_candidates: Vec<String> = if cfg!(target_os = "windows") {
            vec![
                "python.exe".to_string(),
                "python3.exe".to_string(),
                "py.exe".to_string(),
            ]
        } else {
            vec![
                "/usr/local/bin/python3".to_string(),
                "/opt/homebrew/bin/python3".to_string(),
                "/usr/bin/python3".to_string(),
                "python3".to_string(),
            ]
        };
        let python_exe = python_candidates
            .iter()
            .find(|p| Path::new(p).exists() || which_simple(p))
            .cloned()
            .unwrap_or_else(|| String::from("python3"));

        // 1. Try bundled Python source in Resources/python/
        if let Some(dir) = resource_dir {
            let bundled_python = dir.join("python");
            eprintln!("Trying bundled python: {}", bundled_python.display());
            if bundled_python.join("cscode").join("server").join("app.py").exists() {
                let mut cmd = Command::new(&python_exe);
                cmd.env("PYTHONPATH", bundled_python.to_string_lossy().to_string());
                cmd.env("CSCORE_RESOURCE_DIR", dir.to_string_lossy().to_string());
                cmd.env("PATH", &safe_path);
                // Pass API config via environment variables
                cmd.env("CSCODE_API_KEY", option_env!("CSCODE_API_KEY").unwrap_or(""));
                cmd.env("CSCODE_API_BASE", "https://api.scnet.cn/api/llm/v1");
                cmd.env("CSCODE_MODEL", "MiniMax-M2.5");
                cmd.env("CSCODE_PROVIDER", "openai");
                cmd.args(["-m", "cscode", "server", "--port", &port_str, "--host", "127.0.0.1"]);
                cmd.stdout(Stdio::inherit());
                cmd.stderr(Stdio::inherit());

                match cmd.spawn() {
                    Ok(child) => {
                        eprintln!("Started server from bundled python source");
                        self.child = Some(child);
                        return Ok(());
                    }
                    Err(e) => {
                        eprintln!("Bundled python failed: {e}, falling back to dev mode");
                    }
                }
            }
        }

        // 2. Fallback: development project
        let mut possible_paths: Vec<PathBuf> = vec![
            PathBuf::from("/Users/mac/AI/CScode"),
            PathBuf::from("."),
        ];

        if let Ok(cwd) = std::env::current_dir() {
            possible_paths.push(cwd.clone());
            possible_paths.push(cwd.parent().unwrap_or(&cwd).to_path_buf());
        }

        let project_root = possible_paths
            .iter()
            .find(|p| p.join("src/cscode/server/app.py").exists())
            .cloned()
            .ok_or("Could not find project root (src/cscode/server/app.py)")?;

        let src_path = project_root.join("src");
        let python_path = src_path.to_string_lossy().to_string();

        eprintln!("Project root: {}", project_root.display());

        let mut cmd = Command::new(&python_exe);
        cmd.env("PYTHONPATH", &python_path);
        cmd.env("PATH", &safe_path);
        // Pass API config via environment variables
        cmd.env("CSCODE_API_KEY", option_env!("CSCODE_API_KEY").unwrap_or(""));
        cmd.env("CSCODE_API_BASE", "https://api.scnet.cn/api/llm/v1");
        cmd.env("CSCODE_MODEL", "MiniMax-M2.5");
        cmd.env("CSCODE_PROVIDER", "openai");
        if let Some(dir) = resource_dir {
            cmd.env("CSCORE_RESOURCE_DIR", dir.to_string_lossy().to_string());
        }
        cmd.current_dir(&project_root);
        cmd.args(["-m", "cscode", "server", "--port", &port_str, "--host", "127.0.0.1"]);
        cmd.stdout(Stdio::inherit());
        cmd.stderr(Stdio::inherit());

        let child = cmd
            .spawn()
            .map_err(|e| format!("Failed to start backend: {e}"))?;

        self.child = Some(child);
        Ok(())
    }

    fn stop(&mut self) {
        if let Some(ref mut child) = self.child {
            let _ = child.kill();
            let _ = child.wait();
            self.child = None;
        }
    }
}

async fn wait_for_health(port: u16) -> Result<(), String> {
    let url = format!("http://127.0.0.1:{port}/api/health");
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| format!("Failed to create HTTP client: {e}"))?;

    for _ in 0..150 {
        match client.get(&url).send().await {
            Ok(resp) if resp.status().is_success() => return Ok(()),
            _ => tokio::time::sleep(Duration::from_millis(200)).await,
        }
    }
    Err(format!("Backend at {url} did not become ready within 30 seconds"))
}

/// Check if a command name exists in PATH by trying to spawn it with --version
fn which_simple(cmd: &str) -> bool {
    std::process::Command::new(cmd)
        .arg("--version")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .ok()
        .and_then(|mut c| c.wait().ok())
        .map(|s| s.success())
        .unwrap_or(false)
}

#[tauri::command]
async fn open_output_file(filename: String) -> Result<String, String> {
    let safe_name = Path::new(&filename)
        .file_name()
        .ok_or_else(|| "Invalid filename".to_string())?
        .to_string_lossy()
        .to_string();

    let output_dir = std::env::temp_dir().join("cscode-outputs");
    let file_path = output_dir.join(&safe_name);

    if !file_path.exists() {
        // Open the parent directory in file manager so user sees what files exist
        let _ = std::fs::create_dir_all(&output_dir);
        let _ = open_in_file_manager(&output_dir);
        return Err(format!("File not found: {safe_name}"));
    }

    reveal_in_file_manager(&file_path)
        .map_err(|e| format!("Failed to reveal: {e}"))?;

    Ok(String::new())
}

#[cfg(target_os = "macos")]
fn open_in_file_manager(path: &Path) -> Result<(), String> {
    std::process::Command::new("open")
        .arg(path)
        .spawn()
        .map_err(|e| format!("Failed to open: {e}"))?;
    Ok(())
}

#[cfg(target_os = "macos")]
fn reveal_in_file_manager(path: &Path) -> Result<(), String> {
    std::process::Command::new("open")
        .args(["-R", &path.to_string_lossy()])
        .spawn()
        .map_err(|e| format!("Failed to reveal: {e}"))?;
    Ok(())
}

#[cfg(target_os = "linux")]
fn open_in_file_manager(path: &Path) -> Result<(), String> {
    std::process::Command::new("xdg-open")
        .arg(path)
        .spawn()
        .map_err(|e| format!("Failed to open: {e}"))?;
    Ok(())
}

#[cfg(target_os = "linux")]
fn reveal_in_file_manager(path: &Path) -> Result<(), String> {
    // xdg-open doesn't support -R; open the parent dir instead
    if let Some(parent) = path.parent() {
        std::process::Command::new("xdg-open")
            .arg(parent)
            .spawn()
            .map_err(|e| format!("Failed to reveal: {e}"))?;
    }
    Ok(())
}

#[cfg(target_os = "windows")]
fn open_in_file_manager(path: &Path) -> Result<(), String> {
    std::process::Command::new("explorer")
        .arg(path)
        .spawn()
        .map_err(|e| format!("Failed to open: {e}"))?;
    Ok(())
}

#[cfg(target_os = "windows")]
fn reveal_in_file_manager(path: &Path) -> Result<(), String> {
    std::process::Command::new("explorer")
        .args(["/select,", &path.to_string_lossy()])
        .spawn()
        .map_err(|e| format!("Failed to reveal: {e}"))?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port: u16 = 8080;
    let mut backend = BackendState::new(port);

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![open_output_file])
        .setup(move |app| {
            let resource_dir = app.path().resource_dir().ok();

            if let Err(e) = backend.start(resource_dir.as_deref()) {
                eprintln!("Backend start error: {e}");
            }

            let window = app.get_webview_window("main").ok_or("no main window")?;

            tauri::async_runtime::spawn(async move {
                match wait_for_health(port).await {
                    Ok(()) => {
                        let url = url::Url::parse(&format!("http://127.0.0.1:{port}"))
                            .expect("invalid URL");
                        // Fade out the loading page, then navigate
                        let _ = window.eval("document.body.classList.add('fade-out')");
                        tokio::time::sleep(Duration::from_millis(200)).await;
                        let _ = window.navigate(url);
                    }
                    Err(e) => {
                        eprintln!("Health check failed: {e}");
                        let _ = window.eval(
                            "document.body.innerHTML = '<div style=\"display:flex;align-items:center;justify-content:center;height:100vh;background:#1a1a2e;color:#e0e0e0;font-family:sans-serif;text-align:center\"><div><h2>Backend Failed to Start</h2><p>Please ensure Python 3.11+ is installed.</p></div></div>'"
                        );
                    }
                }
            });

            app.manage(Mutex::new(backend));

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if let Some(state) = window.try_state::<Mutex<BackendState>>() {
                    if let Ok(mut backend) = state.lock() {
                        backend.stop();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
