import { useEffect, useCallback, useState } from 'react';
import { Settings, HelpCircle, Menu, X } from 'lucide-react';
import { ThreadsHeader } from '../sidebar/ThreadsHeader';
import { ProjectList } from '../sidebar/ProjectList';
import { useSessionStore } from '../../stores/useSessionStore';
import { useUIStore } from '../../stores/useUIStore';
import { api } from '../../lib/api';


export function Sidebar() {
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);
  const [mobileOpen, setMobileOpen] = useState(false);
  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setSessions = useSessionStore((s) => s.setSessions);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const setMessages = useSessionStore((s) => s.setMessages);
  const addSession = useSessionStore((s) => s.addSession);
  const removeSession = useSessionStore((s) => s.removeSession);
  const updateSessionTitle = useSessionStore((s) => s.updateSessionTitle);

  useEffect(() => {
    api.sessions.list().then(setSessions).catch((e) => console.error('Failed to fetch sessions', e));
  }, [setSessions]);

  const handleSelectSession = useCallback(async (id: string) => {
    console.log('[sidebar] >>> select session id=%s', id);
    const store = useSessionStore.getState();
    // IMPORTANT: Do NOT abort previous session's stream here.
    // The old stream continues to completion — its events (tool steps, response)
    // still belong to that session's store. Aborting would discard TCP buffer data
    // and lose the LLM's response. Only abort when starting a new message for the
    // same session (handled in sendMessage → abortSession).
    const cached = store.sessionMessages[id];
    const cachedVersion = store.sessionMessageVersion[id] || 0;
    console.log('[sidebar] sessionMessages[%s] cached=%s length=%d version=%d activeSessionId=%s', id, cached !== undefined, cached?.length ?? 0, cachedVersion, store.activeSessionId);
    if (cached !== undefined && cached.length > 0) {
      console.log('[sidebar] <<< cached hit, skip fetch');
      setActiveSession(id);
      return;
    }
    setActiveSession(id);
    try {
      console.log('[sidebar] fetching messages for session=%s', id);
      const msgs = await api.sessions.messages(id);
      console.log('[sidebar] fetched %d messages from server for session=%s', msgs.length, id);
      const emptyAssistants = msgs.filter(m => m.role === 'assistant' && !m.content?.trim()).length;
      if (emptyAssistants > 0) console.log('[sidebar] SERVER RETURNED %d EMPTY ASSISTANT MESSAGES!', emptyAssistants);
      const currentStore = useSessionStore.getState();
      if (currentStore.activeSessionId === id) {
        // Version guard: if local appendMessage happened during fetch, discard stale data
        const currentVersion = currentStore.sessionMessageVersion[id] || 0;
        if (currentVersion > cachedVersion) {
          console.log('[sidebar] VERSION CHANGED during fetch (was=%d now=%d): discarding stale server data for session=%s', cachedVersion, currentVersion, id);
          return;
        }
        setMessages(msgs, id);
        console.log('[sidebar] setMessages done for session=%s', id);
      } else {
        console.log('[sidebar] discard fetch: activeSession changed during fetch (now=%s, wanted=%s)', currentStore.activeSessionId, id);
      }
    } catch {
      console.log('[sidebar] fetch failed for session=%s', id);
      const currentStore = useSessionStore.getState();
      if (currentStore.activeSessionId === id) {
        const currentVersion = currentStore.sessionMessageVersion[id] || 0;
        if (currentVersion > cachedVersion) {
          console.log('[sidebar] VERSION CHANGED during failed fetch (was=%d now=%d): not clearing messages for session=%s', cachedVersion, currentVersion, id);
          return;
        }
        setMessages([], id);
      }
    }
    console.log('[sidebar] <<< select session id=%s done', id);
  }, [setActiveSession, setMessages]);

  const handleNewSession = useCallback(async () => {
    // Immediately clear active session so Composer won't route
    // a quick send to the old session during the async gap.
    setActiveSession(null);
    try {
      const session = await api.sessions.create();
      addSession(session);
      setActiveSession(session.id);
      setMessages([], session.id);
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
      if (useSessionStore.getState().activeSessionId === id) {
        setActiveSession(null);
        setMessages([], id);
      }
    } catch (e) {
      console.error('Failed to delete session', e);
    }
  }, [removeSession, setActiveSession, setMessages]);

  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;

  const handleCloseMobile = () => setMobileOpen(false);

  return (
    <>
      {isMobile && (
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="fixed top-14 left-2 z-40 p-2 bg-v2-bg-surface border border-v2-border rounded-md shadow-lg"
        >
          {mobileOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
      )}
      {isMobile && mobileOpen && (
        <div className="fixed inset-0 z-20 bg-black/30" onClick={handleCloseMobile} />
      )}
      <div
        className={`bg-v2-bg-surface border-r border-v2-border flex flex-col h-full transition-all duration-300 ${
          isMobile
            ? mobileOpen
              ? 'fixed inset-0 z-30 w-64'
              : 'hidden'
            : 'w-64'
        }`}
        role="navigation"
        aria-label="Session threads"
      >
        <ThreadsHeader />
        <ProjectList
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onDeleteSession={handleDeleteSession}
          onUpdateSession={updateSessionTitle}
          onImportSession={addSession}
        />
        <div className="mt-auto border-t border-v2-border p-3 flex gap-4">
          <button
            onClick={() => setSettingsOpen(true)}
            className="flex items-center gap-1.5 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors"
          >
            <Settings size={14} />
            Settings
          </button>
          <button
            onClick={() => window.open('https://opencode.ai/docs', '_blank')}
            className="flex items-center gap-1.5 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors"
          >
            <HelpCircle size={14} />
            Help
          </button>
        </div>
      </div>
    </>
  );
}
