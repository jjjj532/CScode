import { useEffect } from 'react';
import { useUIStore, type Mode } from '../../stores/useUIStore';

const modes: { id: Mode; label: string }[] = [
  { id: 'plan', label: 'Plan' },
  { id: 'build', label: 'Build' },
];

export function ModeToggle() {
  const mode = useUIStore((s) => s.mode);
  const setMode = useUIStore((s) => s.setMode);
  const toggleMode = useUIStore((s) => s.toggleMode);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const target = e.target as HTMLElement;
        const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable;
        if (!isInput) {
          e.preventDefault();
          toggleMode();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleMode]);

  return (
    <div className="flex bg-v2-bg-surface rounded-md overflow-hidden text-xs" role="radiogroup" aria-label="Mode selection">
      {modes.map((m) => (
        <button
          key={m.id}
          onClick={() => setMode(m.id)}
          role="radio"
          aria-checked={mode === m.id}
          className={`px-3 py-1 font-medium transition-colors ${
            mode === m.id
              ? m.id === 'plan'
                ? 'bg-v2-accent text-white'
                : 'bg-v2-accent-secondary text-white'
              : 'text-v2-text-muted hover:text-v2-text-secondary'
          }`}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
