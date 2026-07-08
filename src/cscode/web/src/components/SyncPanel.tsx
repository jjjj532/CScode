import { useEffect, useState, useCallback } from 'react';

interface SyncEvent {
  id: number;
  aggregate_id: string;
  seq: number;
  type: string;
  created_at: number;
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

export function SyncPanel() {
  const [events, setEvents] = useState<SyncEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    try {
      const data = await syncRequest<{ events: SyncEvent[] }>('/api/sync/events');
      setEvents(data.events || []);
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Failed to fetch events');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const handlePush = async () => {
    setLoading(true);
    setMessage('');
    try {
      await syncRequest<{ pushed: number }>('/api/sync/push', { method: 'POST' });
      setMessage('Sync pushed successfully');
      await fetchEvents();
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Push failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '16px 0' }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Sync</h3>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
        <button onClick={handlePush} disabled={loading}
          style={{
            background: loading ? '#e5e7eb' : '#3b82f6',
            color: loading ? '#9ca3af' : '#fff',
            border: 'none',
            padding: '6px 16px',
            borderRadius: 6,
            fontSize: 13,
            cursor: loading ? 'not-allowed' : 'pointer',
          }}>
          {loading ? 'Syncing...' : 'Push Sync'}
        </button>
        <button onClick={fetchEvents} disabled={loading}
          style={{
            background: '#f3f4f6',
            border: '1px solid #d1d5db',
            padding: '6px 16px',
            borderRadius: 6,
            fontSize: 13,
            cursor: 'pointer',
          }}>
          Refresh
        </button>
      </div>
      {message && (
        <div style={{ fontSize: 13, marginBottom: 8, color: message.includes('Error') ? '#ef4444' : '#22c55e' }}>
          {message}
        </div>
      )}
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
        {events.length} sync events
      </div>
      <div style={{
        maxHeight: 200,
        overflowY: 'auto',
        border: '1px solid #e5e7eb',
        borderRadius: 6,
        fontSize: 12,
        fontFamily: "'SF Mono', 'Fira Code', monospace",
      }}>
        {events.length === 0 && (
          <div style={{ padding: 12, color: '#9ca3af', textAlign: 'center' }}>
            No sync events
          </div>
        )}
        {events.slice(-20).reverse().map((e) => (
          <div key={e.id} style={{
            padding: '4px 8px',
            borderBottom: '1px solid #f3f4f6',
            display: 'flex',
            gap: 8,
          }}>
            <span style={{ color: '#6b7280', minWidth: 30 }}>#{e.id}</span>
            <span style={{ color: '#3b82f6' }}>{e.type}</span>
            <span style={{ color: '#9ca3af', marginLeft: 'auto' }}>
              {e.aggregate_id.slice(0, 8)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
