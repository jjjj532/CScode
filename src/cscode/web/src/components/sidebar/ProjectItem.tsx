import { useState } from 'react';
import { ChevronRight, ChevronDown, Folder, MessageSquare, X } from 'lucide-react';
import type { Session } from '../../stores/useSessionStore';

interface ProjectGroup {
  name: string;
  sessions: Session[];
}

interface ProjectItemProps {
  project: ProjectGroup;
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string, e: React.MouseEvent) => void;
}

export function ProjectItem({ project, activeSessionId, onSelectSession, onDeleteSession }: ProjectItemProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 w-full px-3 py-1.5 text-sm text-v2-text-secondary hover:text-v2-text-primary transition-colors"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Folder size={14} className="text-v2-text-muted" />
        <span>{project.name}</span>
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
                <span className="truncate">{session.title}</span>
              </button>
              <button
                onClick={(e) => onDeleteSession(session.id, e)}
                className="p-1 mr-1 rounded opacity-0 group-hover:opacity-100 hover:bg-v2-bg-deep text-v2-text-muted hover:text-red-400 transition-all"
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
