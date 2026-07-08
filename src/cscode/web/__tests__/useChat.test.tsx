import { renderHook, act } from '@testing-library/react';
import { useChat } from '../src/hooks/useChat';

// Polyfill TextEncoder/TextDecoder for jsdom
if (typeof TextDecoder === 'undefined') {
  const { TextEncoder, TextDecoder } = require('util');
  global.TextEncoder = TextEncoder;
  global.TextDecoder = TextDecoder;
}

const mockState: Record<string, any> = {
  appendMessage: jest.fn(),
  setActiveSession: jest.fn((id: string) => { mockState.activeSessionId = id; }),
  addSession: jest.fn(),
  setLoading: jest.fn((id: string, loading: boolean) => { mockState.sessionLoading[id] = loading; }),
  updateSessionTitle: jest.fn(),
  setSessionThinking: jest.fn(),
  applyEvent: jest.fn(),
  sessions: [],
  sessionMessages: {},
  sessionLoading: {},
  sessionToolCalls: {},
  sessionThinking: {},
  sessionAttachments: {},
  activeSessionId: 'session_active',
};

jest.mock('../src/stores/useSessionStore', () => ({
  useSessionStore: Object.assign(
    (selector: any) => selector(mockState),
    { getState: () => mockState },
  ),
}));

class MockReadableStream {
  getReader() {
    let done = false;
    return {
      read: async () => {
        if (done) return { done: true, value: undefined };
        done = true;
        return { done: false, value: new TextEncoder().encode('data: {"type":"complete","content":"Hello"}\n\n') };
      },
    };
  }
}

const mockFetch = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  global.fetch = mockFetch;
  // Default: mock POST /api/sessions returns a session
  mockFetch.mockImplementation((url: string) => {
    if (url === '/api/session' || url.includes('/api/session')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ id: 'session_mock', title: 'New Session', created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
      });
    }
    return Promise.resolve({
      ok: true,
      body: new MockReadableStream(),
    });
  });
});

describe('useChat Hook', () => {
  test('returns sendMessage and stop', () => {
    const { result } = renderHook(() => useChat());
    expect(result.current.sendMessage).toBeDefined();
    expect(result.current.stop).toBeDefined();
  });

  test('sendMessage creates session then calls fetch and appends user message', async () => {
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.sendMessage('Hello');
    });
    expect(mockState.addSession).toHaveBeenCalled();
    expect(mockState.setActiveSession).toHaveBeenCalled();
    expect(mockState.setSessionThinking).toHaveBeenCalled();
    expect(mockState.appendMessage).toHaveBeenCalledWith(expect.objectContaining({ role: 'user', content: 'Hello' }), expect.any(String));
    expect(mockFetch).toHaveBeenCalledWith('/api/chat/stream', expect.objectContaining({
      method: 'POST',
      body: expect.stringContaining('"message":"Hello"'),
    }));
  });

  test('sendMessage with sessionId includes it in the request', async () => {
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.sendMessage('Hello', 'session_123');
    });
    expect(mockState.addSession).not.toHaveBeenCalled();
    expect(mockFetch).toHaveBeenCalledWith('/api/chat/stream', expect.objectContaining({
      method: 'POST',
      body: expect.stringContaining('"session_id":"session_123"'),
    }));
  });

  test('sendMessage sets loading state', async () => {
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.sendMessage('Hello', 'session_123');
    });
    expect(mockState.setLoading).toHaveBeenCalledWith('session_123', true);
    expect(mockState.setLoading).toHaveBeenCalledWith('session_123', false);
  });

  test('sendMessage handles API errors', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/api/session')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 'session_err' }) });
      }
      return Promise.resolve({ ok: false, status: 500 });
    });
    const { result } = renderHook(() => useChat());
    await act(async () => {
      try { await result.current.sendMessage('Hello', 'session_active'); } catch {}
    });
    expect(mockState.appendMessage).toHaveBeenCalledWith(expect.objectContaining({
      role: 'assistant',
      content: expect.stringContaining('Error'),
    }), 'session_active');
  });

  test('sendMessage dispatches tool.called event to applyEvent', async () => {
    class MockToolStream {
      getReader() {
        let calls = 0;
        return {
          read: async () => {
            if (calls >= 2) return { done: true, value: undefined };
            const data = calls === 0
              ? 'data: {"type":"tool.called","data":{"name":"browser","args":{},"round":1,"max":5}}\n\n'
              : 'data: {"type":"complete","content":"Done"}\n\n';
            calls++;
            return { done: false, value: new TextEncoder().encode(data) };
          },
        };
      }
    }
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/session' || url.includes('/api/session')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 'session_tool', title: 'Test' }) });
      }
      return Promise.resolve({ ok: true, body: new MockToolStream() });
    });
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.sendMessage('Hello');
    });
    expect(mockState.applyEvent).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
      type: 'tool.called',
      data: expect.objectContaining({ name: 'browser', round: 1 }),
    }));
  });

  test('stop calls abort on the controller', async () => {
    const abortSpy = jest.fn();
    const originalAbort = AbortController.prototype.abort;
    AbortController.prototype.abort = abortSpy;
    let resolveFetch: (v: any) => void;
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/api/session')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 'session_mock' }) });
      }
      return new Promise((resolve) => { resolveFetch = resolve; });
    });
    const { result } = renderHook(() => useChat());
    // Start sendMessage but don't await (keep chat fetch pending)
    result.current.sendMessage('Hello');
    // Flush microtasks so session creation completes (setLoading + setActiveSession update mock state)
    await act(async () => {});
    // Now stop should find a loading session and call abort
    act(() => { result.current.stop(); });
    expect(abortSpy).toHaveBeenCalled();
    AbortController.prototype.abort = originalAbort;
    if (resolveFetch) resolveFetch({ ok: true, body: new MockReadableStream() });
  });
});
