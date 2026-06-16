import { useSessionStore } from '../../stores/useSessionStore';
import { ProjectItem } from './ProjectItem';

export function ProjectList() {
  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);

  const projects = [
    {
      name: 'AI-CScode',
      sessions: sessions,
    },
  ];

  return (
    <div className="flex-1 overflow-y-auto py-1">
      {projects.map((project) => (
        <ProjectItem
          key={project.name}
          project={project}
          activeSessionId={activeSessionId}
          onSelectSession={setActiveSession}
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
