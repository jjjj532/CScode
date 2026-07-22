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

  permissionRules: {
    list: () => request<Array<{ id: number; action: string; resource: string; effect: string }>>('/api/permission-rules'),
    create: (rule: { action: string; resource: string; effect: string }) => request<{ id: number }>('/api/permission-rules', {
      method: 'POST',
      body: JSON.stringify(rule),
    }),
    delete: (id: number) => request<void>(`/api/permission-rules/${id}`, { method: 'DELETE' }),
    update: (id: number, rule: { action?: string; resource?: string; effect?: string }) => request<{ id: number; action: string; resource: string; effect: string }>(`/api/permission-rules/${id}`, {
      method: 'PUT',
      body: JSON.stringify(rule),
    }),
  },

  /** Singular alias — maps to /api/session/* (backend aliases) */
  session: {
    list: () => request<Session[]>('/api/session'),
    create: () => request<Session>('/api/session', { method: 'POST', body: '{}' }),
    delete: (id: string) => request<void>(`/api/session/${id}`, { method: 'DELETE' }),
    update: (id: string, data: { title: string }) => request<void>(`/api/session/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    export: (id: string) => request<Record<string, unknown>>(`/api/session/${id}/export`, { method: 'POST' }),
    import: (data: Record<string, unknown>) => request<Session>('/api/session/import', { method: 'POST', body: JSON.stringify(data) }),
    messages: (id: string) => request<Message[]>(`/api/session/${id}/messages`),
  },

  /** Plural (legacy) — kept for backward compat */
  sessions: {
    list: () => request<Session[]>('/api/sessions'),
    create: () => request<Session>('/api/sessions', { method: 'POST', body: '{}' }),
    delete: (id: string) => request<void>(`/api/sessions/${id}`, { method: 'DELETE' }),
    update: (id: string, data: { title: string }) => request<void>(`/api/sessions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    export: (id: string) => request<Record<string, unknown>>(`/api/sessions/${id}/export`, { method: 'POST' }),
    import: (data: Record<string, unknown>) => request<Session>('/api/sessions/import', { method: 'POST', body: JSON.stringify(data) }),
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
  },

  health: {
    check: () => request<{ status: string }>('/api/health'),
  },
};
