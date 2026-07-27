/**
 * Error Monitor Tests
 */
import { initErrorMonitor, teardownErrorMonitor } from '../src/lib/errorMonitor';

beforeEach(() => {
  jest.clearAllMocks();
  teardownErrorMonitor();
  global.fetch = jest.fn();
});

afterEach(() => {
  teardownErrorMonitor();
});

describe('initErrorMonitor', () => {
  test('registers window.onerror handler', () => {
    const prev = window.onerror;
    initErrorMonitor();
    expect(window.onerror).not.toBe(prev);
  });

  test('registers window.onunhandledrejection handler', () => {
    const prev = window.onunhandledrejection;
    initErrorMonitor();
    expect(window.onunhandledrejection).not.toBe(prev);
  });

  test('POSTs error to /api/logs/error on window.onerror', () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });

    initErrorMonitor();
    // Call window.onerror directly (jsdom re-throws ErrorEvent dispatching)
    const handler = window.onerror as OnErrorEventHandler;
    handler('Something broke', 'http://localhost/app.js', 42, 10, new Error('Something broke'));

    expect(global.fetch).toHaveBeenCalledWith('/api/logs/error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: expect.stringContaining('Something broke'),
    });
  });

  test('POSTs unhandled rejection to /api/logs/error', () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });

    initErrorMonitor();
    const handler = window.onunhandledrejection as (event: { reason: unknown }) => void;
    handler({ reason: new Error('Promise failed') });

    expect(global.fetch).toHaveBeenCalledWith('/api/logs/error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: expect.stringContaining('Promise failed'),
    });
  });

  test('does not throw if POST fails', () => {
    (global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'));

    initErrorMonitor();
    const handler = window.onerror as OnErrorEventHandler;
    expect(() => {
      handler('Boom', undefined, undefined, undefined, new Error('Boom'));
    }).not.toThrow();
  });

  test('debounces duplicate errors within 30s window', () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });

    initErrorMonitor();
    const handler = window.onerror as OnErrorEventHandler;
    handler('Dup', undefined, undefined, undefined, new Error('Dup'));
    handler('Dup', undefined, undefined, undefined, new Error('Dup'));

    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});

describe('teardownErrorMonitor', () => {
  test('restores window.onerror to pre-init value', () => {
    const prev = window.onerror;
    initErrorMonitor();
    teardownErrorMonitor();
    expect(window.onerror).toBe(prev);
  });

  test('restores window.onunhandledrejection to pre-init value', () => {
    const prev = window.onunhandledrejection;
    initErrorMonitor();
    teardownErrorMonitor();
    expect(window.onunhandledrejection).toBe(prev);
  });
});
