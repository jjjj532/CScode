/**
 * API Client Tests
 * 测试API客户端功能
 */
import { api, setRetryConfig } from '../src/lib/api';
import { Config } from '../src/types';

// Mock global fetch
global.fetch = jest.fn();

describe('api', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('chat', () => {
    test('sends message and returns response', async () => {
      const mockStream = {
        ok: true,
        body: {
          getReader: () => ({
            read: async () => ({ done: true, value: new Uint8Array() }),
          }),
        },
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce(mockStream);

      const result = await api.chat.send('Hello');

      expect(result.ok).toBe(true);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/chat',
        expect.objectContaining({ method: 'POST' })
      );
    });

    test('sends message with session id', async () => {
      const mockStream = { ok: true };

      (global.fetch as jest.Mock).mockResolvedValueOnce(mockStream);

      await api.chat.send('Hello', 'session_123');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/chat',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ message: 'Hello', session_id: 'session_123' }),
        })
      );
    });
  });

  describe('session (singular alias)', () => {
    test('session.list calls /api/session', async () => {
      const mockSessions = [
        { id: 'session_1', title: 'Session 1' },
      ];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockSessions,
      });
      const result = await api.session.list();
      expect(result).toEqual(mockSessions);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/session',
        expect.any(Object)
      );
    });

    test('session.create calls POST /api/session', async () => {
      const mockSession = { id: 'session_123', title: 'New Session' };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockSession,
      });
      const result = await api.session.create();
      expect(result).toEqual(mockSession);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/session',
        expect.objectContaining({ method: 'POST' })
      );
    });

    test('session.delete calls DELETE /api/session/:id', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      });
      await api.session.delete('session_123');
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/session/session_123',
        expect.objectContaining({ method: 'DELETE' })
      );
    });

    test('session.messages calls /api/session/:id/messages', async () => {
      const mockMessages = [
        { id: '1', role: 'user', content: 'Hello' },
      ];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockMessages,
      });
      const result = await api.session.messages('session_123');
      expect(result).toEqual(mockMessages);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/session/session_123/messages',
        expect.any(Object)
      );
    });
  });

  describe('sessions', () => {
    test('lists all sessions', async () => {
      const mockSessions = [
        { id: 'session_1', title: 'Session 1' },
        { id: 'session_2', title: 'Session 2' },
      ];

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockSessions,
      });

      const result = await api.sessions.list();

      expect(result).toEqual(mockSessions);
    });

    test('creates a new session', async () => {
      const mockSession = {
        id: 'session_123',
        title: 'New Session',
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockSession,
      });

      const result = await api.sessions.create();

      expect(result).toEqual(mockSession);
    });

    test('deletes a session', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({ 
        ok: true,
        json: async () => ({}),
      });

      await api.sessions.delete('session_123');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/sessions/session_123',
        expect.objectContaining({ method: 'DELETE' })
      );
    });

    test('gets session messages', async () => {
      const mockMessages = [
        { id: '1', role: 'user', content: 'Hello' },
        { id: '2', role: 'assistant', content: 'Hi there!' },
      ];

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockMessages,
      });

      const result = await api.sessions.messages('session_123');

      expect(result).toEqual(mockMessages);
    });
  });

  describe('config', () => {
    test('gets current config', async () => {
      const mockConfig: Partial<Config> = {
        provider: 'openai',
        model: 'gpt-4',
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockConfig,
      });

      const result = await api.config.get();

      expect(result).toEqual(mockConfig);
    });

    test('saves config', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      });

      const config: Partial<Config> = { provider: 'anthropic', model: 'claude-3' };
      await api.config.save(config);

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/config',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(config),
        })
      );
    });
  });

  describe('health', () => {
    test('checks health status', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'ok' }),
      });

      const result = await api.health.check();

      expect(result).toEqual({ status: 'ok' });
    });
  });
});

describe('retry logic', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setRetryConfig({ maxRetries: 2, baseDelayMs: 50 });
  });

  test('succeeds on first attempt without retry', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });
    const result = await api.health.check();
    expect(result).toEqual({ status: 'ok' });
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  test('retries on network error and succeeds', async () => {
    (global.fetch as jest.Mock)
      .mockRejectedValueOnce(new TypeError('Network error'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'ok' }),
      });

    const result = await api.health.check();
    expect(result).toEqual({ status: 'ok' });
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  test('throws after exhausting retries', async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new TypeError('Network error'));

    await expect(api.health.check()).rejects.toThrow('Network error');
    expect(global.fetch).toHaveBeenCalledTimes(3); // initial + 2 retries
  });

  test('does NOT retry on HTTP 4xx error', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => 'Bad request',
    });

    await expect(api.health.check()).rejects.toThrow('API error 400');
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
