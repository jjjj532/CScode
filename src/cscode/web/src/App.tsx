import { useEffect } from 'react';
import { Titlebar } from './components/layout/Titlebar';
import { Sidebar } from './components/layout/Sidebar';
import { MainContent } from './components/layout/MainContent';
import { SettingsPanel } from './components/ui/SettingsPanel';
import { useUIStore } from './stores/useUIStore';
import { useConfigStore } from './stores/useConfigStore';
import { useSessionStore } from './stores/useSessionStore';

function App() {
  const settingsOpen = useUIStore((s) => s.settingsOpen);
  const setConfig = useConfigStore((s) => s.setConfig);
  const setSessions = useSessionStore((s) => s.setSessions);

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then((data) => {
        if (data && data.provider) setConfig(data);
      })
      .catch(() => {});
  }, [setConfig]);

  useEffect(() => {
    fetch('/api/sessions')
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setSessions(data);
      })
      .catch(() => {});
  }, [setSessions]);

  return (
    <div className="h-full flex flex-col bg-v2-bg-deep text-v2-text-primary">
      <Titlebar />
      <div className="flex-1 flex min-h-0">
        <Sidebar />
        <MainContent />
      </div>
      {settingsOpen && <SettingsPanel />}
    </div>
  );
}

export default App;
