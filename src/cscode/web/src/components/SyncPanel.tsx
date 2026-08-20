import { useSync } from '../hooks/useSync';

export function SyncPanel() {
  const { status, events, push, refresh } = useSync();
  const syncing = status === 'syncing';

  return (
    <div style={{ padding: '16px 0' }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Sync</h3>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
        <button onClick={() => { void push(); }} disabled={syncing}
          style={{
            background: syncing ? '#e5e7eb' : '#3b82f6',
            color: syncing ? '#9ca3af' : '#fff',
            border: 'none',
            padding: '6px 16px',
            borderRadius: 6,
            fontSize: 13,
            cursor: syncing ? 'not-allowed' : 'pointer',
          }}>
          {syncing ? 'Syncing...' : 'Push Sync'}
        </button>
        <button onClick={() => { void refresh(); }} disabled={syncing}
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
        {status === 'complete' && (
          <span style={{ fontSize: 12, color: '#22c55e' }}>✓ Synced</span>
        )}
        {status === 'error' && (
          <span style={{ fontSize: 12, color: '#ef4444' }}>Sync failed</span>
        )}
      </div>
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