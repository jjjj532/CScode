import { useCallback, useRef, useState } from 'react';

export interface SyncEvent {
  id: number;
  aggregate_id: string;
  seq: number;
  type: string;
  created_at: number;
}

export type SyncStatus = 'idle' | 'syncing' | 'complete' | 'error';

export interface UseSyncResult {
  status: SyncStatus;
  lastSyncedAt: number | null;
  events: SyncEvent[];
  push: () => Promise<void>;
  refresh: () => Promise<void>;
}

async function syncRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Sync error ${res.status}: ${text}`);
  }
  return res.json();
}

/** Sync 状态机：串行化 push/refresh，busy 期间忽略重复调用。 */
export function useSync(): UseSyncResult {
  const [status, setStatus] = useState<SyncStatus>('idle');
  const [events, setEvents] = useState<SyncEvent[]>([]);
  const [lastSyncedAt, setLastSyncedAt] = useState<number | null>(null);
  const busyRef = useRef(false);
  const lastSyncedRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setStatus('syncing');
    try {
      const data = await syncRequest<SyncEvent[]>('/api/sync/events');
      setEvents(data);
      const now = Date.now();
      lastSyncedRef.current = now;
      setLastSyncedAt(now);
      setStatus('complete');
    } catch {
      setStatus('error');
    } finally {
      busyRef.current = false;
    }
  }, []);

  const push = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setStatus('syncing');
    try {
      await syncRequest<{ pushed: number }>('/api/sync/push', { method: 'POST' });
      // 推送成功后拉取最新事件
      const data = await syncRequest<SyncEvent[]>('/api/sync/events');
      setEvents(data);
      const now = Date.now();
      lastSyncedRef.current = now;
      setLastSyncedAt(now);
      setStatus('complete');
    } catch {
      setStatus('error');
    } finally {
      busyRef.current = false;
    }
  }, []);

  return { status, lastSyncedAt, events, push, refresh };
}
