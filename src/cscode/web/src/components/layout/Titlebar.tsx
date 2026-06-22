import { useEffect, useState } from 'react';
import { ModeToggle } from '../ui/ModeToggle';

export function Titlebar() {
  const [cwd, setCwd] = useState('~/AI/CScode');

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((data) => {
        if (data.workspace) setCwd(data.workspace);
      })
      .catch(() => {});
  }, []);

  return (
    <div className="flex items-center justify-between h-10 px-4 bg-v2-bg-deep border-b border-v2-border select-none draggable" role="banner">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-semibold text-v2-text-primary">CScode</span>
        <span className="text-v2-text-muted">—</span>
        <span className="text-v2-text-secondary">{cwd}</span>
      </div>
      <div className="flex items-center gap-3">
        <ModeToggle />
      </div>
    </div>
  );
}
