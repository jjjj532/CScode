import { useState } from 'react';
import { ChevronRight, ChevronDown, Folder, MessageSquare } from 'lucide-react';
import type { Session } from '../../stores/useSessionStore';

interface ProjectGroup {
  name: string;
  sessions: Session[];
}

interface ProjectItemProps {
  project: ProjectGroup;
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
}

export function ProjectItem({ project, activeSessionId, onSelectSession }: ProjectItemProps) {
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
            <button
              key={session.id}
              onClick={() => onSelectSession(session.id)}
              className={`flex items-center gap-1.5 w-full px-3 py-1.5 text-sm rounded-md transition-colors ${
                activeSessionId === session.id
                  ? 'bg-v2-bg-base text-v2-text-primary'
                  : 'text-v2-text-muted hover:text-v2-text-secondary hover:bg-v2-bg-base/50'
              }`}
            >
              <MessageSquare size={14} />
              <span className="truncate">{session.title}</span>
            </button>
          ))}
          {project.sessions.length === 0 && (
            <div className="px-3 py-1 text-xs text-v2-text-muted italic">No sessions</div>
          )}
        </div>
      )}
    </div>
  );
}
