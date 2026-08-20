import type { Config } from '../stores/useConfigStore';
import type { Session, Message } from '../stores/useSessionStore';
import { ENDPOINTS, MANUAL_ENDPOINTS } from './api/generated/endpoints';
import type { ApiEndpoint } from './api/generated/endpoints';

const BASE = '';

/** 从端点表解析路径模板并插值路径参数。 */
function endpointPath(
  endpoint: ApiEndpoint,
  params?: Record<string, string | number>,
): string {
  let path = endpoint.path;
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      path = path.replace(`{${key}}`, String(value));
    }
  }
  return path;
}

interface RetryConfig {
  maxRetries: number;
  baseDelayMs: number;
}

let retryConfig: RetryConfig = { maxRetries: 2, baseDelayMs: 1000 };

export function setRetryConfig(config: Partial<RetryConfig>): void {
  retryConfig = { ...retryConfig, ...config };
}

async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retryConfig.maxRetries; attempt++) {
    try {
      const res = await fetch(`${BASE}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`API error ${res.status}: ${text}`);
      }
      return res.json();
    } catch (err) {
      // Don't retry on HTTP errors (4xx/5xx) — only network errors
      if (err instanceof Error && !(err instanceof TypeError)) {
        throw err;
      }
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt < retryConfig.maxRetries) {
        await delay(retryConfig.baseDelayMs * Math.pow(2, attempt));
      }
    }
  }

  throw lastError ?? new Error('Request failed');
}

export const api = {
  config: {
    get: () => request<Config>(ENDPOINTS.getConfig.path),
    save: (config: Config) => request<Config>(ENDPOINTS.saveConfig.path, {
      method: ENDPOINTS.saveConfig.method,
      body: JSON.stringify(config),
    }),
  },

  permissionRules: {
    list: () => request<Array<{ id: number; action: string; resource: string; effect: string }>>(ENDPOINTS.listPermissionRules.path),
    create: (rule: { action: string; resource: string; effect: string }) => request<{ id: number }>(ENDPOINTS.createPermissionRule.path, {
      method: ENDPOINTS.createPermissionRule.method,
      body: JSON.stringify(rule),
    }),
    delete: (id: number) => request<void>(endpointPath(ENDPOINTS.deletePermissionRule, { rule_id: id }), { method: ENDPOINTS.deletePermissionRule.method }),
    update: (id: number, rule: { action?: string; resource?: string; effect?: string }) => request<{ id: number; action: string; resource: string; effect: string }>(endpointPath(ENDPOINTS.updatePermissionRule, { rule_id: id }), {
      method: ENDPOINTS.updatePermissionRule.method,
      body: JSON.stringify(rule),
    }),
  },

  /** Singular alias — maps to /api/session/* (backend aliases) */
  session: {
    list: () => request<Session[]>(MANUAL_ENDPOINTS.listSessionAlias.path),
    create: () => request<Session>(MANUAL_ENDPOINTS.createSessionAlias.path, { method: MANUAL_ENDPOINTS.createSessionAlias.method, body: '{}' }),
    delete: (id: string) => request<void>(endpointPath(MANUAL_ENDPOINTS.deleteSessionAlias, { session_id: id }), { method: MANUAL_ENDPOINTS.deleteSessionAlias.method }),
    update: (id: string, data: { title: string }) => request<void>(endpointPath(MANUAL_ENDPOINTS.updateSessionAlias, { session_id: id }), { method: MANUAL_ENDPOINTS.updateSessionAlias.method, body: JSON.stringify(data) }),
    export: (id: string) => request<Record<string, unknown>>(endpointPath(MANUAL_ENDPOINTS.exportSessionAlias, { session_id: id }), { method: MANUAL_ENDPOINTS.exportSessionAlias.method }),
    import: (data: Record<string, unknown>) => request<Session>(MANUAL_ENDPOINTS.importSessionAlias.path, { method: MANUAL_ENDPOINTS.importSessionAlias.method, body: JSON.stringify(data) }),
    messages: (id: string) => request<Message[]>(endpointPath(MANUAL_ENDPOINTS.sessionMessagesAlias, { session_id: id })),
  },

  /** Plural (legacy) — kept for backward compat */
  sessions: {
    list: () => request<Session[]>(ENDPOINTS.listSessions.path),
    create: () => request<Session>(ENDPOINTS.createSession.path, { method: ENDPOINTS.createSession.method, body: '{}' }),
    delete: (id: string) => request<void>(endpointPath(ENDPOINTS.deleteSession, { session_id: id }), { method: ENDPOINTS.deleteSession.method }),
    update: (id: string, data: { title: string }) => request<void>(endpointPath(ENDPOINTS.updateSession, { session_id: id }), { method: ENDPOINTS.updateSession.method, body: JSON.stringify(data) }),
    export: (id: string) => request<Record<string, unknown>>(endpointPath(ENDPOINTS.exportSession, { session_id: id }), { method: ENDPOINTS.exportSession.method }),
    import: (data: Record<string, unknown>) => request<Session>(ENDPOINTS.importSession.path, { method: ENDPOINTS.importSession.method, body: JSON.stringify(data) }),
    messages: (id: string) => request<Message[]>(endpointPath(ENDPOINTS.getSessionMessages, { session_id: id })),
  },

  chat: {
    send: (message: string, sessionId?: string, files?: string[]) => {
      const body: Record<string, unknown> = { message };
      if (sessionId) body.session_id = sessionId;
      if (files?.length) body.files = files;
      return fetch(ENDPOINTS.chat.path, {
        method: ENDPOINTS.chat.method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    },
  },

  health: {
    check: () => request<{ status: string }>(ENDPOINTS.health.path),
  },
};
