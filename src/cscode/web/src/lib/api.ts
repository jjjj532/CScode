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

  permission: {
    list: () => request<Array<{ id: string; pattern: string; allow: boolean; label: string }>>('/api/permission/saved'),
    create: (rule: { pattern: string; allow: boolean; label?: string }) => request<{ id: string }>('/api/permission/saved', {
      method: 'POST',
      body: JSON.stringify(rule),
    }),
    delete: (id: string) => request<void>(`/api/permission/saved/${id}`, { method: 'DELETE' }),
  },

  session: {
    list: () => request<Session[]>('/api/session'),
    create: () => request<Session>('/api/session', { method: 'POST', body: '{}' }),
    delete: (id: string) => request<void>(`/api/session/${id}`, { method: 'DELETE' }),
    update: (id: string, data: { title: string }) => request<void>(`/api/session/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    exportSession: (id: string) => request<Record<string, unknown>>(`/api/session/${id}/export`),
    importSession: (data: Record<string, unknown>) => request<Session>('/api/session/import', { method: 'POST', body: JSON.stringify(data) }),
    messages: (id: string) => request<Message[]>(`/api/session/${id}/messages`),
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
  },

  health: {
    check: () => request<{ status: string }>('/api/health'),
  },

  files: {
    search: (q: string) => request<string[]>(`/api/fs/find?q=${encodeURIComponent(q)}`),
  },
};
