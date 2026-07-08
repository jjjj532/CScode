import { useEffect, useState, useCallback } from 'react';

interface ShareEntry {
  id: string;
  session_id: string;
  created_at: number;
  expires_at: number | null;
}

async function shareRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Share error ${res.status}: ${text}`);
  }
  return res.json();
}

export function ShareDialog() {
  const [shares, setShares] = useState<ShareEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedSession, setSelectedSession] = useState('');
  const [message, setMessage] = useState('');

  const fetchShares = useCallback(async () => {
    try {
      const data = await shareRequest<{ shares: ShareEntry[] }>('/api/share');
      setShares(data.shares || []);
    } catch {
      // backend may not have /api/share list endpoint
    }
  }, []);

  useEffect(() => {
    fetchShares();
  }, [fetchShares]);

  const handleCreate = async () => {
    if (!selectedSession.trim()) return;
    setLoading(true);
    setMessage('');
    try {
      await shareRequest('/api/share', {
        method: 'POST',
        body: JSON.stringify({ session_id: selectedSession.trim() }),
      });
      setMessage('Share created');
      setSelectedSession('');
      await fetchShares();
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Create failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    setLoading(true);
    try {
      await shareRequest(`/api/share/${id}`, { method: 'DELETE' });
      await fetchShares();
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '16px 0' }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Share</h3>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <input
          value={selectedSession}
          onChange={(e) => setSelectedSession(e.target.value)}
          placeholder="Session ID to share"
          style={{
            flex: 1,
            border: '1px solid #d1d5db',
            borderRadius: 6,
            padding: '6px 10px',
            fontSize: 13,
          }}
        />
        <button onClick={handleCreate} disabled={loading || !selectedSession.trim()}
          style={{
            background: '#3b82f6',
            color: '#fff',
            border: 'none',
            padding: '6px 16px',
            borderRadius: 6,
            fontSize: 13,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading || !selectedSession.trim() ? 0.5 : 1,
          }}>
          Share
        </button>
      </div>

      {message && (
        <div style={{ fontSize: 13, marginBottom: 8, color: message.includes('Error') || message.includes('fail') ? '#ef4444' : '#22c55e' }}>
          {message}
        </div>
      )}

      <div style={{
        maxHeight: 200,
        overflowY: 'auto',
        border: '1px solid #e5e7eb',
        borderRadius: 6,
        fontSize: 12,
      }}>
        {shares.length === 0 && (
          <div style={{ padding: 12, color: '#9ca3af', textAlign: 'center' }}>
            No shared sessions
          </div>
        )}
        {shares.map((s) => (
          <div key={s.id} style={{
            padding: '6px 8px',
            borderBottom: '1px solid #f3f4f6',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <span style={{ fontFamily: "'SF Mono', monospace", fontSize: 11, color: '#6b7280', flex: 1 }}>
              {s.session_id.slice(0, 12)}...
            </span>
            <button onClick={() => handleDelete(s.id)}
              style={{
                background: 'none',
                border: '1px solid #e5e7eb',
                borderRadius: 4,
                padding: '2px 8px',
                fontSize: 11,
                color: '#ef4444',
                cursor: 'pointer',
              }}>
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
