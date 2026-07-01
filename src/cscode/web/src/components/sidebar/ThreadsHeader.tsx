import { useSessionStore } from '../../stores/useSessionStore';
import { useToastStore } from '../../stores/useToastStore';
import { api } from '../../lib/api';
import { Filter, ArrowUpDown, Eye, Plus } from 'lucide-react';

export function ThreadsHeader() {
  const addSession = useSessionStore((s) => s.addSession);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const setMessages = useSessionStore((s) => s.setMessages);
  const addToast = useToastStore((s) => s.addToast);

  const handleAddSession = async () => {
    try {
      const session = await api.sessions.create();
      addSession(session);
      setActiveSession(session.id);
      setMessages([], session.id);
    } catch (e) {
      addToast('Failed to create session', 'error');
    }
  };

  return (
    <div className="flex items-center justify-between px-3 py-2 border-b border-v2-border">
      <span className="text-xs font-medium text-v2-text-muted tracking-wider">THREADS</span>
      <div className="flex items-center gap-1">
        <button
          className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors"
          title="Filter threads"
          aria-label="Filter threads"
          onClick={() => addToast('Filter feature coming soon', 'info')}
        >
          <Filter size={14} />
        </button>
        <button
          className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors"
          title="Sort threads"
          aria-label="Sort threads"
          onClick={() => addToast('Sort feature coming soon', 'info')}
        >
          <ArrowUpDown size={14} />
        </button>
        <button
          className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors"
          title="Refresh sessions"
          aria-label="Refresh sessions"
          onClick={() => {
            api.sessions.list().then((sessions) => {
              useSessionStore.getState().setSessions(sessions);
              addToast('Sessions refreshed', 'success');
            }).catch(() => addToast('Failed to refresh sessions', 'error'));
          }}
        >
          <Eye size={14} />
        </button>
        <button
          className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors"
          title="New session"
          aria-label="Create new session"
          onClick={handleAddSession}
        >
          <Plus size={14} />
        </button>
      </div>
    </div>
  );
}
