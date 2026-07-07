import { useState, useEffect, useCallback } from 'react';
import { Search, Settings, Plus, Sun, Moon, X, Sidebar, Cpu, MessageSquare } from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';
import { useSessionStore } from '../../stores/useSessionStore';
import { useConfigStore } from '../../stores/useConfigStore';
import { useToastStore } from '../../stores/useToastStore';
import { api } from '../../lib/api';
import type { Session } from '../../stores/useSessionStore';

interface Command {
  id: string;
  label: string;
  icon: typeof Search;
  keywords?: string;
  action: () => void;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const theme = useUIStore((s) => s.theme);
  const setTheme = useUIStore((s) => s.setTheme);
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);
  const mode = useUIStore((s) => s.mode);
  const toggleMode = useUIStore((s) => s.toggleMode);
  const addSession = useSessionStore((s) => s.addSession);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const setMessages = useSessionStore((s) => s.setMessages);
  const sessions = useSessionStore((s) => s.sessions);
  const addToast = useToastStore((s) => s.addToast);

  const switchSession = useCallback((sess: Session) => {
    setActiveSession(sess.id);
    setMessages([], sess.id);
    setOpen(false);
  }, [setActiveSession, setMessages]);

  const commands: Command[] = [
    {
      id: 'new-session',
      label: 'New Session',
      icon: Plus,
      keywords: 'create chat conversation',
      action: async () => {
        try {
          const session = await api.session.create();
          addSession(session);
          setActiveSession(session.id);
          setMessages([], session.id);
        } catch (e) {
          addToast('Failed to create session', 'error');
          console.error('Failed to create session', e);
        }
        setOpen(false);
      },
    },
    {
      id: 'settings',
      label: 'Open Settings',
      icon: Settings,
      keywords: 'config preferences',
      action: () => {
        setSettingsOpen(true);
        setOpen(false);
      },
    },
    {
      id: 'toggle-sidebar',
      label: sidebarOpen ? 'Close Sidebar' : 'Open Sidebar',
      icon: Sidebar,
      keywords: 'panel toggle hide show',
      action: () => {
        setSidebarOpen(!sidebarOpen);
        setOpen(false);
      },
    },
    {
      id: 'toggle-mode',
      label: `Switch to ${mode === 'plan' ? 'Build' : 'Plan'} Mode`,
      icon: Cpu,
      keywords: 'mode plan build switch',
      action: () => {
        toggleMode();
        setOpen(false);
      },
    },
    {
      id: 'theme-light',
      label: 'Switch to Light Theme',
      icon: Sun,
      keywords: 'light theme white bright',
      action: () => {
        setTheme('opencode-light');
        setOpen(false);
      },
    },
    {
      id: 'theme-dark',
      label: 'Switch to Dark Theme',
      icon: Moon,
      keywords: 'dark theme black night',
      action: () => {
        setTheme('opencode-dark');
        setOpen(false);
      },
    },
  ];

  const dynamicCommands: Command[] = sessions.slice(0, 5).map((sess) => ({
    id: `session-${sess.id}`,
    label: `Switch to: ${sess.title || 'Untitled'}`,
    icon: MessageSquare,
    keywords: `session ${sess.title}`,
    action: () => switchSession(sess),
  }));

  const allCommands = [...commands, ...dynamicCommands];

  const filteredCommands = allCommands.filter((cmd) => {
    const q = query.toLowerCase();
    return cmd.label.toLowerCase().includes(q) || (cmd.keywords || '').includes(q);
  });

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      setOpen(true);
    }
    if (!open) return;

    if (e.key === 'Escape') {
      setOpen(false);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, filteredCommands.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && filteredCommands[selectedIndex]) {
      filteredCommands[selectedIndex].action();
    }
  }, [open, filteredCommands, selectedIndex, setSettingsOpen, setTheme]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24">
      <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
      <div className="relative w-full max-w-lg bg-v2-bg-base border border-v2-border rounded-v2 shadow-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-v2-border">
          <Search size={16} className="text-v2-text-muted" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command..."
            className="flex-1 bg-transparent text-sm text-v2-text-primary placeholder-v2-text-muted outline-none"
            autoFocus
          />
          <button onClick={() => setOpen(false)} aria-label="Close command palette" className="text-v2-text-muted hover:text-v2-text-secondary">
            <X size={16} />
          </button>
        </div>
        <div className="max-h-64 overflow-y-auto py-1">
          {filteredCommands.map((cmd, i) => (
            <button
              key={cmd.id}
              onClick={cmd.action}
              className={`w-full flex items-center gap-3 px-4 py-2 text-sm text-left transition-colors ${
                i === selectedIndex
                  ? 'bg-v2-accent/10 text-v2-accent'
                  : 'text-v2-text-secondary hover:bg-v2-bg-surface'
              }`}
            >
              <cmd.icon size={16} />
              {cmd.label}
            </button>
          ))}
          {filteredCommands.length === 0 && (
            <div className="px-4 py-3 text-sm text-v2-text-muted">No commands found</div>
          )}
        </div>
        <div className="px-4 py-2 border-t border-v2-border flex items-center justify-between text-[10px] text-v2-text-muted">
          <span>↑↓ Navigate</span>
          <span>↵ Select</span>
          <span>Esc Close</span>
        </div>
      </div>
    </div>
  );
}
