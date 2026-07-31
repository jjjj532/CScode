use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::Manager;
use tauri::tray::TrayIconBuilder;
use tauri::menu::{Menu, MenuItem};

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
            let cmd = format!("for /f \"tokens=5\" %a in ('netstat -aon ^| findstr :{}') do taskkill /f /pid %a", port);
            let output = Command::new("cmd")
                .args(["/C", &cmd])
                .output()
                .map_err(|e| format!("Failed to kill process: {e}"))?;
        }
        Ok(())
    }

    fn start(&mut self, resource_dir: Option<&Path>) -> Result<(), String> {
        self.kill_port(self.port)?;
        std::thread::sleep(std::time::Duration::from_millis(500));

        let port_str = self.port.to_string();

        // Build safe PATH for Playwright Chromium discovery
        let path = std::env::var("PATH").unwrap_or_default();
        let safe_path = if cfg!(target_os = "windows") {
            format!("{};{}", path, std::env::var("APPDATA").unwrap_or_default())
        } else {
            format!(
                "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:{}",
                path
            )
        };

        // 1. Try PyInstaller-bundled binary (self-contained, no Python needed)
        if let Some(dir) = resource_dir {
            #[cfg(target_os = "windows")]
            let backend_bin = dir.join("resources").join("cscode-backend").join("cscode-backend.exe");
            #[cfg(not(target_os = "windows"))]
            let backend_bin = dir.join("resources").join("cscode-backend").join("cscode-backend");

            eprintln!("Checking for PyInstaller binary: {}", backend_bin.display());
            if backend_bin.exists() {
                let mut cmd = Command::new(&backend_bin);
                cmd.env("PATH", &safe_path);
                if let Ok(key) = std::env::var("CSCODE_API_KEY") {
                    if !key.is_empty() { cmd.env("CSCODE_API_KEY", key); }
                }
                if let Ok(base) = std::env::var("CSCODE_API_BASE") {
                    if !base.is_empty() { cmd.env("CSCODE_API_BASE", base); }
                }
                if let Ok(model) = std::env::var("CSCODE_MODEL") {
                    if !model.is_empty() { cmd.env("CSCODE_MODEL", model); }
                }
                if let Ok(provider) = std::env::var("CSCODE_PROVIDER") {
                    if !provider.is_empty() { cmd.env("CSCODE_PROVIDER", provider); }
                }
                cmd.env("CSCODE_RESOURCE_DIR", dir.to_string_lossy().to_string());
                cmd.args(["--port", &port_str, "--host", "127.0.0.1"]);
                cmd.stdout(Stdio::inherit());
                cmd.stderr(Stdio::inherit());

                match cmd.spawn() {
                    Ok(child) => {
                        eprintln!("Started PyInstaller backend from bundled resources");
                        self.child = Some(child);
                        return Ok(());
                    }
                    Err(e) => {
                        eprintln!("PyInstaller backend failed: {e}, falling back to Python");
                    }
                }
            }
        }

        // 2. Fallback: legacy Python-based launch (for development)
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

        // 2a. Try legacy bundled resources (python_deps/ + python/)
        if let Some(dir) = resource_dir {
            let python_src = dir.join("resources").join("python");
            let python_deps = dir.join("resources").join("python_deps");
            if python_src.join("cscode").join("server").join("app.py").exists() {
                let mut pythonpath = python_src.to_string_lossy().to_string();
                if python_deps.exists() {
                    pythonpath.push(':');
                    pythonpath.push_str(&python_deps.to_string_lossy());
                }

                let mut cmd = Command::new(&python_exe);
                cmd.env("PYTHONPATH", &pythonpath);
                cmd.env("CSCODE_RESOURCE_DIR", dir.to_string_lossy().to_string());
                cmd.env("PATH", &safe_path);
                if let Ok(key) = std::env::var("CSCODE_API_KEY") {
                    if !key.is_empty() { cmd.env("CSCODE_API_KEY", key); }
                }
                if let Ok(base) = std::env::var("CSCODE_API_BASE") {
                    if !base.is_empty() { cmd.env("CSCODE_API_BASE", base); }
                }
                if let Ok(model) = std::env::var("CSCODE_MODEL") {
                    if !model.is_empty() { cmd.env("CSCODE_MODEL", model); }
                }
                if let Ok(provider) = std::env::var("CSCODE_PROVIDER") {
                    if !provider.is_empty() { cmd.env("CSCODE_PROVIDER", provider); }
                }
                cmd.args(["-m", "cscode", "server", "--port", &port_str, "--host", "127.0.0.1"]);
                cmd.stdout(Stdio::inherit());
                cmd.stderr(Stdio::inherit());

                match cmd.spawn() {
                    Ok(child) => {
                        eprintln!("Started server from legacy bundled resources");
                        self.child = Some(child);
                        return Ok(());
                    }
                    Err(e) => {
                        eprintln!("Legacy bundled resources failed: {e}, falling back to dev mode");
                    }
                }
            }
        }

        // 2b. Fallback: development project
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
        if let Ok(key) = std::env::var("CSCODE_API_KEY") {
            if !key.is_empty() { cmd.env("CSCODE_API_KEY", key); }
        }
        if let Ok(base) = std::env::var("CSCODE_API_BASE") {
            if !base.is_empty() { cmd.env("CSCODE_API_BASE", base); }
        }
        if let Ok(model) = std::env::var("CSCODE_MODEL") {
            if !model.is_empty() { cmd.env("CSCODE_MODEL", model); }
        }
        if let Ok(provider) = std::env::var("CSCODE_PROVIDER") {
            if !provider.is_empty() { cmd.env("CSCODE_PROVIDER", provider); }
        }
        if let Some(dir) = resource_dir {
            cmd.env("CSCODE_RESOURCE_DIR", dir.to_string_lossy().to_string());
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

/// Check if a process is alive by sending signal 0 (Unix) or checking tasklist (Windows).
fn is_process_alive(pid: u32) -> bool {
    #[cfg(unix)]
    {
        std::process::Command::new("kill")
            .args(["-0", &pid.to_string()])
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
    }
    #[cfg(windows)]
    {
        let output = std::process::Command::new("tasklist")
            .args(["/FI", &format!("PID eq {}", pid), "/NH"])
            .output();
        match output {
            Ok(o) => String::from_utf8_lossy(&o.stdout).contains(&pid.to_string()),
            Err(_) => false,
        }
    }
}

/// Spawn a monitoring task that restarts the backend if it exits unexpectedly.
/// Uses a separate Arc<Mutex> so the async task doesn't fight Tauri's State lifetimes.
fn spawn_auto_restart(
    backend_arc: Arc<Mutex<BackendState>>,
    resource_dir: Option<PathBuf>,
) {
    tauri::async_runtime::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(5)).await;

            let needs_restart = {
                let guard = match backend_arc.lock() {
                    Ok(g) => g,
                    Err(_) => continue,
                };
                match &guard.child {
                    Some(c) => !is_process_alive(c.id()),
                    None => false,
                }
            };

            if needs_restart {
                eprintln!("Backend process exited, restarting...");
                match backend_arc.lock() {
                    Ok(mut guard) => {
                        guard.child = None;
                        if let Err(e) = guard.start(resource_dir.as_deref()) {
                            eprintln!("Auto-restart failed: {e}");
                        }
                    }
                    Err(_) => eprintln!("Auto-restart: mutex poisoned"),
                }
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port: u16 = 8080;
    let backend = BackendState::new(port);
    let backend_arc = Arc::new(Mutex::new(backend));

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new()
            .with_handler(|app_handle, _shortcut, event| {
                if event.state == tauri_plugin_global_shortcut::ShortcutState::Pressed {
                    if let Some(w) = app_handle.get_webview_window("main") {
                        if w.is_visible().unwrap_or(true) {
                            let _ = w.hide();
                        } else {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                }
            })
            .build())
        .invoke_handler(tauri::generate_handler![open_output_file])
        .setup(move |app| {
            let resource_dir = app.path().resource_dir().ok();
            let resource_dir_clone = resource_dir.clone();
            let arc_for_restart = backend_arc.clone();

            // Start backend via the Arc
            {
                let mut guard = backend_arc.lock().unwrap();
                if let Err(e) = guard.start(resource_dir.as_deref()) {
                    eprintln!("Backend start error: {e}");
                }
            }

            let window = app.get_webview_window("main").ok_or("no main window")?;

            // ── Tray Icon ──────────────────────────────────────────
            let show_item = MenuItem::with_id(app, "show", "Show CScode", true, None::<&str>)?;
            let hide_item = MenuItem::with_id(app, "hide", "Hide", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let tray_menu = Menu::with_items(app, &[&show_item, &hide_item, &quit_item])?;

            let arc_for_tray = backend_arc.clone();
            TrayIconBuilder::new()
                .menu(&tray_menu)
                .on_menu_event(move |app_handle, event| {
                    match event.id().as_ref() {
                        "show" => {
                            if let Some(w) = app_handle.get_webview_window("main") {
                                let _ = w.show();
                                let _ = w.set_focus();
                            }
                        }
                        "hide" => {
                            if let Some(w) = app_handle.get_webview_window("main") {
                                let _ = w.hide();
                            }
                        }
                        "quit" => {
                            if let Ok(mut guard) = arc_for_tray.lock() {
                                guard.stop();
                            }
                            app_handle.exit(0);
                        }
                        _ => {}
                    }
                })
                .build(app)?;

            // ── Global Shortcuts ───────────────────────────────────
            use tauri_plugin_global_shortcut::GlobalShortcutExt;
            match app.global_shortcut().register("CmdOrCtrl+Alt+S") {
                Ok(_) => eprintln!("Registered global shortcut: Cmd+Opt+S"),
                Err(e) => eprintln!("Failed to register global shortcut: {e}"),
            }

            // ── Backend health check + navigation ──────────────────
            tauri::async_runtime::spawn(async move {
                match wait_for_health(port).await {
                    Ok(()) => {
                        let url = url::Url::parse(&format!("http://127.0.0.1:{port}"))
                            .expect("invalid URL");
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

            // ── Auto-restart monitor ───────────────────────────────
            spawn_auto_restart(arc_for_restart, resource_dir_clone);

            // Store the Arc in Tauri's managed state for window events
            app.manage(backend_arc.clone());

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if let Some(state) = window.try_state::<Arc<Mutex<BackendState>>>() {
                    if let Ok(mut guard) = state.lock() {
                        guard.stop();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
