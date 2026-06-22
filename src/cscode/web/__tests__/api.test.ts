/**
 * API Client Tests
 * 测试API客户端功能
 */
import { api } from '../src/lib/api';
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
