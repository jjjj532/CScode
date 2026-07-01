import { useState, useRef, useEffect } from 'react';
import { ChevronRight, ChevronDown, Folder, MessageSquare, X, Download, Upload } from 'lucide-react';
import type { Session } from '../../stores/useSessionStore';
import { api } from '../../lib/api';
import { useToastStore } from '../../stores/useToastStore';

interface ProjectGroup {
  name: string;
  sessions: Session[];
}

interface ProjectItemProps {
  project: ProjectGroup;
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string, e: React.MouseEvent) => void;
  onUpdateSession: (id: string, title: string) => void;
  onImportSession: (session: Session) => void;
}

export function ProjectItem({ project, activeSessionId, onSelectSession, onDeleteSession, onUpdateSession, onImportSession }: ProjectItemProps) {
  const [expanded, setExpanded] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const addToast = useToastStore((s) => s.addToast);

  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  const handleStartEdit = (session: Session, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(session.id);
    setEditValue(session.title);
  };

  const handleSaveEdit = async (sessionId: string) => {
    const newTitle = editValue.trim();
    if (!newTitle) {
      setEditingId(null);
      return;
    }
    try {
      await api.session.update(sessionId, { title: newTitle });
      onUpdateSession(sessionId, newTitle);
      addToast('Session renamed', 'success');
    } catch {
      addToast('Failed to rename session', 'error');
    }
    setEditingId(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent, sessionId: string) => {
    if (e.key === 'Enter') handleSaveEdit(sessionId);
    if (e.key === 'Escape') setEditingId(null);
  };

  const handleExport = async (sessionId: string, title: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const data = await api.session.exportSession(sessionId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${title.replace(/[^a-z0-9]/gi, '_')}.json`;
      a.click();
      URL.revokeObjectURL(url);
      addToast('Session exported', 'success');
    } catch {
      addToast('Failed to export session', 'error');
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const session = await api.session.importSession(data);
      onImportSession(session);
      addToast('Session imported', 'success');
    } catch {
      addToast('Failed to import session', 'error');
    }
    e.target.value = '';
  };

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 w-full px-3 py-1.5 text-sm text-v2-text-secondary hover:text-v2-text-primary transition-colors"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Folder size={14} className="text-v2-text-muted" />
        <span>{project.name}</span>
        <label className="ml-auto p-1 rounded hover:bg-v2-bg-deep text-v2-text-muted hover:text-v2-text-secondary cursor-pointer">
          <Upload size={12} />
          <input type="file" accept=".json" onChange={handleImport} className="hidden" aria-label="Import session" />
        </label>
      </button>
      {expanded && (
        <div className="ml-4">
          {project.sessions.map((session) => (
            <div
              key={session.id}
              className={`group flex items-center rounded-md transition-colors ${
                activeSessionId === session.id
                  ? 'bg-v2-bg-base'
                  : 'hover:bg-v2-bg-base/50'
              }`}
            >
              <button
                onClick={() => onSelectSession(session.id)}
                className="flex items-center gap-1.5 flex-1 px-3 py-1.5 text-sm text-v2-text-muted hover:text-v2-text-secondary truncate"
              >
                <MessageSquare size={14} />
                {editingId === session.id ? (
                  <input
                    ref={inputRef}
                    type="text"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onBlur={() => handleSaveEdit(session.id)}
                    onKeyDown={(e) => handleKeyDown(e, session.id)}
                    onClick={(e) => e.stopPropagation()}
                    className="bg-v2-bg-deep border border-v2-accent rounded px-1 text-v2-text-primary w-32"
                  />
                ) : (
                  <span
                    onDoubleClick={(e) => handleStartEdit(session, e)}
                    className="truncate cursor-text"
                    title="Double-click to rename"
                  >
                    {session.title}
                  </span>
                )}
              </button>
              <button
                onClick={(e) => handleExport(session.id, session.title, e)}
                aria-label="Export session"
                className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-v2-bg-deep text-v2-text-muted hover:text-v2-accent transition-all"
                title="Export session"
              >
                <Download size={12} />
              </button>
              <button
                onClick={(e) => onDeleteSession(session.id, e)}
                aria-label="Delete session"
                className="p-1 mr-1 rounded opacity-0 group-hover:opacity-100 hover:bg-v2-bg-deep text-v2-text-muted hover:text-red-400 transition-all"
                title="Delete session"
              >
                <X size={12} />
              </button>
            </div>
          ))}
          {project.sessions.length === 0 && (
            <div className="px-3 py-1 text-xs text-v2-text-muted italic">No sessions</div>
          )}
        </div>
      )}
    </div>
  );
}
