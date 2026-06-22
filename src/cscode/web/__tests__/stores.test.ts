/**
 * Store Tests
 * 测试Zustand状态管理
 */
import { renderHook, act } from '@testing-library/react';
import { useConfigStore } from '../src/stores/useConfigStore';
import { useSessionStore } from '../src/stores/useSessionStore';

describe('useConfigStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useConfigStore.setState({
      config: null,
      loading: false,
    });
  });

  test('provides initial config values', () => {
    const { result } = renderHook(() => useConfigStore());
    
    expect(result.current.config).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  test('setConfig updates config values', () => {
    const { result } = renderHook(() => useConfigStore());
    
    const newConfig = {
      provider: 'anthropic',
      model: 'claude-3',
      api_base: null,
      max_tokens: 2000,
      temperature: 0.7,
      top_p: 1.0,
      system_prompt: null,
    };
    
    act(() => {
      result.current.setConfig(newConfig);
    });
    
    expect(result.current.config?.provider).toBe('anthropic');
    expect(result.current.config?.model).toBe('claude-3');
  });

  test('updateConfig updates partial config values', () => {
    const { result } = renderHook(() => useConfigStore());
    
    // First set a config
    act(() => {
      result.current.setConfig({
        provider: 'openai',
        model: 'gpt-4',
        api_base: null,
        max_tokens: 2000,
        temperature: 0.7,
        top_p: 1.0,
        system_prompt: null,
      });
    });
    
    // Then update partial
    act(() => {
      result.current.updateConfig({ temperature: 0.5 });
    });
    
    expect(result.current.config?.provider).toBe('openai');
    expect(result.current.config?.temperature).toBe(0.5);
  });

  test('setLoading updates loading state', () => {
    const { result } = renderHook(() => useConfigStore());
    
    act(() => {
      result.current.setLoading(true);
    });
    
    expect(result.current.loading).toBe(true);
  });

  test('updateConfig returns null when config is null', () => {
    const { result } = renderHook(() => useConfigStore());
    
    act(() => {
      result.current.updateConfig({ provider: 'test' });
    });
    
    expect(result.current.config).toBeNull();
  });
});

describe('useSessionStore', () => {
  beforeEach(() => {
    useSessionStore.setState({
      sessions: [],
      sessionMessages: {},
      sessionLoading: {},
      sessionToolCalls: {},
      sessionThinking: {},
      sessionAttachments: {},
      activeSessionId: null,
    });
  });

  test('provides initial session values', () => {
    const { result } = renderHook(() => useSessionStore());
    
    expect(result.current.sessions).toEqual([]);
    expect(result.current.sessionMessages).toEqual({});
    expect(result.current.activeSessionId).toBeNull();
    expect(result.current.sessionLoading).toEqual({});
  });

  test('setSessions updates sessions list', () => {
    const { result } = renderHook(() => useSessionStore());
    
    const sessions = [
      { id: 'session_1', title: 'Session 1', created_at: '2024-01-01', updated_at: '2024-01-01' },
      { id: 'session_2', title: 'Session 2', created_at: '2024-01-02', updated_at: '2024-01-02' },
    ];
    
    act(() => {
      result.current.setSessions(sessions);
    });
    
    expect(result.current.sessions).toHaveLength(2);
    expect(result.current.sessions[0].title).toBe('Session 1');
  });

  test('addSession adds new session', () => {
    const { result } = renderHook(() => useSessionStore());
    
    const newSession = {
      id: 'session_new',
      title: 'New Session',
      created_at: '2024-01-03',
      updated_at: '2024-01-03',
    };
    
    act(() => {
      result.current.addSession(newSession);
    });
    
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.sessions[0].id).toBe('session_new');
  });

  test('removeSession removes session and its messages', () => {
    const { result } = renderHook(() => useSessionStore());
    
    // Add sessions and messages first
    act(() => {
      result.current.setSessions([
        { id: 'session_1', title: 'Session 1', created_at: '2024-01-01', updated_at: '2024-01-01' },
        { id: 'session_2', title: 'Session 2', created_at: '2024-01-02', updated_at: '2024-01-02' },
      ]);
      result.current.setMessages([{ role: 'user', content: 'Hello' }], 'session_1');
      result.current.setMessages([{ role: 'user', content: 'World' }], 'session_2');
    });
    
    // Remove one
    act(() => {
      result.current.removeSession('session_1');
    });
    
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.sessions[0].id).toBe('session_2');
    expect(result.current.sessionMessages['session_1']).toBeUndefined();
    expect(result.current.sessionMessages['session_2']).toEqual([{ role: 'user', content: 'World' }]);
  });

  test('setMessages updates messages for a specific session', () => {
    const { result } = renderHook(() => useSessionStore());
    
    const messages = [
      { role: 'user', content: 'Hello' },
      { role: 'assistant', content: 'Hi there!' },
    ];
    
    act(() => {
      result.current.setMessages(messages, 'session_1');
    });
    
    expect(result.current.sessionMessages['session_1']).toHaveLength(2);
    expect(result.current.sessionMessages['session_1'][0].content).toBe('Hello');
    expect(result.current.sessionMessages['session_2']).toBeUndefined();
  });

  test('appendMessage adds message to a specific session with auto-generated id', () => {
    const { result } = renderHook(() => useSessionStore());
    
    act(() => {
      result.current.appendMessage({ role: 'user', content: 'Test message' }, 'session_1');
    });
    
    expect(result.current.sessionMessages['session_1']).toHaveLength(1);
    expect(result.current.sessionMessages['session_1'][0].content).toBe('Test message');
    expect(result.current.sessionMessages['session_1'][0].id).toBeDefined();
    expect(result.current.sessionMessages['session_1'][0].id).toMatch(/^msg_/);
  });

  test('appendMessage appends to existing messages for a session', () => {
    const { result } = renderHook(() => useSessionStore());
    
    act(() => {
      result.current.setMessages([{ role: 'user', content: 'First' }], 'session_1');
      result.current.appendMessage({ role: 'user', content: 'Second' }, 'session_1');
    });
    
    expect(result.current.sessionMessages['session_1']).toHaveLength(2);
    expect(result.current.sessionMessages['session_1'][0].content).toBe('First');
    expect(result.current.sessionMessages['session_1'][1].content).toBe('Second');
  });

  test('appendMessage does not affect other sessions', () => {
    const { result } = renderHook(() => useSessionStore());
    
    act(() => {
      result.current.setMessages([{ role: 'user', content: 'Session 1' }], 'session_1');
      result.current.appendMessage({ role: 'user', content: 'Session 2' }, 'session_2');
    });
    
    expect(result.current.sessionMessages['session_1']).toHaveLength(1);
    expect(result.current.sessionMessages['session_2']).toHaveLength(1);
    expect(result.current.sessionMessages['session_1'][0].content).toBe('Session 1');
    expect(result.current.sessionMessages['session_2'][0].content).toBe('Session 2');
  });

  test('setActiveSession updates active session id', () => {
    const { result } = renderHook(() => useSessionStore());
    
    act(() => {
      result.current.setActiveSession('session_123');
    });
    
    expect(result.current.activeSessionId).toBe('session_123');
  });

  test('updateSessionTitle updates session title', () => {
    const { result } = renderHook(() => useSessionStore());
    
    act(() => {
      result.current.setSessions([
        { id: 'session_1', title: 'Old Title', created_at: '2024-01-01', updated_at: '2024-01-01' },
      ]);
    });
    
    act(() => {
      result.current.updateSessionTitle('session_1', 'New Title');
    });
    
    expect(result.current.sessions[0].title).toBe('New Title');
  });

  test('setLoading updates loading state', () => {
    const { result } = renderHook(() => useSessionStore());
    
    act(() => {
      result.current.setLoading('session_1', true);
    });
    
    expect(result.current.sessionLoading['session_1']).toBe(true);
  });
});
