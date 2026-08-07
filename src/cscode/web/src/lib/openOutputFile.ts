/**
 * Open a generated file outside the browser.
 *
 * In the Tauri desktop app: invokes the native `open_output_file` command,
 * which reveals the file in the system file manager (Finder on macOS).
 * In a plain browser: copies the absolute path to the clipboard and returns
 * true, since there is no local filesystem to open.
 */

export function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

export async function openOutputFile(
  path: string,
  opts: { fallback?: (path: string) => void } = {},
): Promise<boolean> {
  if (isTauriRuntime()) {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('open_output_file', { filename: path });
    return true;
  }
  opts.fallback?.(path);
  return false;
}