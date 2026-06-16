import { ProjectItem } from './ProjectItem';
import type { Session } from '../../stores/useSessionStore';

interface ProjectListProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string, e: React.MouseEvent) => void;
}

export function ProjectList({ sessions, activeSessionId, onSelectSession, onDeleteSession }: ProjectListProps) {
  const projects = [
    { name: 'AI-CScode', sessions },
  ];

  return (
    <div className="flex-1 overflow-y-auto py-1">
      {projects.map((project) => (
        <ProjectItem
          key={project.name}
          project={project}
          activeSessionId={activeSessionId}
          onSelectSession={onSelectSession}
          onDeleteSession={onDeleteSession}
        />
      ))}
      {sessions.length === 0 && (
        <div className="px-6 py-8 text-center text-sm text-v2-text-muted">
          No sessions yet. Start a new chat.
        </div>
      )}
    </div>
  );
}
