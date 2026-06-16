import { useEffect, useCallback } from 'react';
import { Settings, HelpCircle } from 'lucide-react';
import { ThreadsHeader } from '../sidebar/ThreadsHeader';
import { ProjectList } from '../sidebar/ProjectList';
import { useSessionStore } from '../../stores/useSessionStore';
import { useUIStore } from '../../stores/useUIStore';
import { api } from '../../lib/api';

export function Sidebar() {
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setSessions = useSessionStore((s) => s.setSessions);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const setMessages = useSessionStore((s) => s.setMessages);
  const addSession = useSessionStore((s) => s.addSession);
  const removeSession = useSessionStore((s) => s.removeSession);

  useEffect(() => {
    api.sessions.list().then(setSessions).catch(() => {});
  }, [setSessions]);

  const handleSelectSession = useCallback(async (id: string) => {
    setActiveSession(id);
    try {
      const msgs = await api.sessions.messages(id);
      setMessages(msgs);
    } catch {
      setMessages([]);
    }
  }, [setActiveSession, setMessages]);

  const handleNewSession = useCallback(async () => {
    try {
      const session = await api.sessions.create();
      addSession(session);
      setActiveSession(session.id);
      setMessages([]);
    } catch (e) {
      console.error('Failed to create session', e);
    }
  }, [addSession, setActiveSession, setMessages]);

  const handleDeleteSession = useCallback(async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this session?')) return;
    try {
      await api.sessions.delete(id);
      removeSession(id);
      if (activeSessionId === id) {
        setActiveSession(null);
        setMessages([]);
      }
    } catch (e) {
      console.error('Failed to delete session', e);
    }
  }, [activeSessionId, removeSession, setActiveSession, setMessages]);

  return (
    <div className="w-64 bg-v2-bg-surface border-r border-v2-border flex flex-col h-full">
      <ThreadsHeader />
      <ProjectList
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
      />
      <div className="mt-auto border-t border-v2-border p-3 flex gap-4">
        <button
          onClick={() => setSettingsOpen(true)}
          className="flex items-center gap-1.5 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors"
        >
          <Settings size={14} />
          Settings
        </button>
        <button className="flex items-center gap-1.5 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors">
          <HelpCircle size={14} />
          Help
        </button>
      </div>
    </div>
  );
}
