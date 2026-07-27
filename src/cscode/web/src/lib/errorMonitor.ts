/**
 * Error Monitor — captures unhandled errors and unhandled promise rejections
 * and POSTs them to /api/logs/error for backend-side monitoring.
 *
 * Usage: call initErrorMonitor() once at app startup.
 */

const DEBOUNCE_MS = 30_000;

// Track recent error messages to avoid flooding the backend
const recentErrors = new Map<string, number>();

function shouldReport(message: string): boolean {
  const now = Date.now();
  const last = recentErrors.get(message);
  if (last && now - last < DEBOUNCE_MS) {
    return false;
  }
  recentErrors.set(message, now);
  return true;
}

let originalOnError: typeof window.onerror = null;
let originalOnRejection: typeof window.onunhandledrejection = null;

export function initErrorMonitor(): void {
  if (originalOnError !== null) return; // already initialized

  originalOnError = window.onerror;
  originalOnRejection = window.onunhandledrejection;

  window.onerror = (message, source, lineno, colno, error) => {
    const msg = typeof message === 'string' ? message : String(message);
    if (!shouldReport(msg)) return;

    fetch('/api/logs/error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: msg,
        stack: error?.stack || '',
        url: source || window.location.href,
        user_agent: navigator.userAgent,
        detail: { lineno, colno },
      }),
    }).catch(() => {
      // Silently swallow — don't cascade errors from the error reporter
    });
  };

  window.onunhandledrejection = (event) => {
    const reason = event.reason;
    const msg = reason?.message || String(reason || 'Unhandled rejection');
    if (!shouldReport(msg)) return;

    fetch('/api/logs/error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: msg,
        stack: reason?.stack || '',
        url: window.location.href,
        user_agent: navigator.userAgent,
        detail: { type: 'unhandledrejection' },
      }),
    }).catch(() => {
      // Silently swallow
    });
  };
}

export function teardownErrorMonitor(): void {
  if (originalOnError !== null) {
    window.onerror = originalOnError;
    originalOnError = null;
  }
  if (originalOnRejection !== null) {
    window.onunhandledrejection = originalOnRejection;
    originalOnRejection = null;
  }
  recentErrors.clear();
}
