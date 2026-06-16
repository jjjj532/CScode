import type { Config } from '../stores/useConfigStore';
import type { Session, Message } from '../stores/useSessionStore';

const BASE = '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  config: {
    get: () => request<Config>('/api/config'),
    save: (config: Config) => request<Config>('/api/config', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  },

  sessions: {
    list: () => request<Session[]>('/api/sessions'),
    create: () => request<Session>('/api/sessions', { method: 'POST' }),
    delete: (id: string) => request<void>(`/api/sessions/${id}`, { method: 'DELETE' }),
    messages: (id: string) => request<Message[]>(`/api/sessions/${id}/messages`),
  },

  chat: {
    send: (message: string, sessionId?: string, files?: string[]) => {
      const body: Record<string, unknown> = { message };
      if (sessionId) body.session_id = sessionId;
      if (files?.length) body.files = files;
      return fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    },
    stream: (message: string, sessionId?: string) => {
      const params = new URLSearchParams({ message });
      if (sessionId) params.set('session_id', sessionId);
      return fetch(`/api/chat/stream?${params}`, { method: 'POST' });
    },
  },

  health: {
    check: () => request<{ status: string }>('/api/health'),
  },
};
