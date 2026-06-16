import { Settings, HelpCircle } from 'lucide-react';
import { ThreadsHeader } from '../sidebar/ThreadsHeader';
import { ProjectList } from '../sidebar/ProjectList';
import { useUIStore } from '../../stores/useUIStore';

export function Sidebar() {
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);

  return (
    <div className="w-64 bg-v2-bg-surface border-r border-v2-border flex flex-col h-full">
      <ThreadsHeader />
      <ProjectList />
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
