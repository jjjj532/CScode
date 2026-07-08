import { useEffect, useState, useCallback } from 'react';

interface CredentialEntry {
  id: string;
  provider: string;
  key_type: string;
  created_at: number;
}

async function credRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Credential error ${res.status}: ${text}`);
  }
  return res.json();
}

const PROVIDERS = ['openai', 'anthropic', 'gemini', 'ollama', 'azure', 'openrouter'];

export function CredentialPanel() {
  const [credentials, setCredentials] = useState<CredentialEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState('openai');
  const [keyValue, setKeyValue] = useState('');
  const [message, setMessage] = useState('');

  const fetchCredentials = useCallback(async () => {
    try {
      const data = await credRequest<{ credentials: CredentialEntry[] }>('/api/credentials');
      setCredentials(data.credentials || []);
    } catch {
      // endpoint may use different response shape
    }
  }, []);

  useEffect(() => {
    fetchCredentials();
  }, [fetchCredentials]);

  const handleAdd = async () => {
    if (!keyValue.trim()) return;
    setLoading(true);
    setMessage('');
    try {
      await credRequest('/api/credentials', {
        method: 'POST',
        body: JSON.stringify({ provider, key: keyValue.trim() }),
      });
      setMessage(`Added credential for ${provider}`);
      setKeyValue('');
      await fetchCredentials();
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Add failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    setLoading(true);
    try {
      await credRequest(`/api/credentials/${id}`, { method: 'DELETE' });
      await fetchCredentials();
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '16px 0' }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Credentials</h3>

      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <select value={provider} onChange={(e) => setProvider(e.target.value)}
          style={{
            border: '1px solid #d1d5db',
            borderRadius: 6,
            padding: '6px 8px',
            fontSize: 13,
            background: '#fff',
          }}>
          {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <input
          value={keyValue}
          onChange={(e) => setKeyValue(e.target.value)}
          placeholder="API key"
          type="password"
          style={{
            flex: 1,
            border: '1px solid #d1d5db',
            borderRadius: 6,
            padding: '6px 10px',
            fontSize: 13,
          }}
        />
        <button onClick={handleAdd} disabled={loading || !keyValue.trim()}
          style={{
            background: '#3b82f6',
            color: '#fff',
            border: 'none',
            padding: '6px 16px',
            borderRadius: 6,
            fontSize: 13,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading || !keyValue.trim() ? 0.5 : 1,
          }}>
          Add
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
        {credentials.length === 0 && (
          <div style={{ padding: 12, color: '#9ca3af', textAlign: 'center' }}>
            No saved credentials
          </div>
        )}
        {credentials.map((c) => (
          <div key={c.id} style={{
            padding: '6px 8px',
            borderBottom: '1px solid #f3f4f6',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <span style={{ fontWeight: 500, color: '#374151', minWidth: 80 }}>{c.provider}</span>
            <span style={{ fontFamily: "'SF Mono', monospace", fontSize: 11, color: '#6b7280', flex: 1 }}>
              {c.key_type}
            </span>
            <button onClick={() => handleDelete(c.id)}
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
