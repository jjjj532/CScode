import { ProjectItem } from './ProjectItem';
import type { Session } from '../../stores/useSessionStore';
import { EmptyState } from '../ui/EmptyState';

interface ProjectListProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string, e: React.MouseEvent) => void;
  onUpdateSession: (id: string, title: string) => void;
  onImportSession: (session: Session) => void;
}

export function ProjectList({ sessions, activeSessionId, onSelectSession, onDeleteSession, onUpdateSession, onImportSession }: ProjectListProps) {
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
          onUpdateSession={onUpdateSession}
          onImportSession={onImportSession}
        />
      ))}
      {sessions.length === 0 && (
        <EmptyState
          icon="💬"
          title="No sessions yet"
          description="Start a new chat to begin."
        />
      )}
    </div>
  );
}
