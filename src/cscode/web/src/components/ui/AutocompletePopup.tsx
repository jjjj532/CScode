import { useState, useEffect, useRef, useCallback } from 'react';

interface Suggestion {
  type: 'file' | 'tool';
  label: string;
  description?: string;
}

const KNOWN_TOOLS: Suggestion[] = [
  { type: 'tool', label: 'Read', description: 'Read file contents' },
  { type: 'tool', label: 'Write', description: 'Write content to file' },
  { type: 'tool', label: 'Edit', description: 'Edit a file' },
  { type: 'tool', label: 'Bash', description: 'Execute shell command' },
  { type: 'tool', label: 'Grep', description: 'Search file contents' },
  { type: 'tool', label: 'Glob', description: 'Find files by pattern' },
  { type: 'tool', label: 'Ls', description: 'List directory' },
  { type: 'tool', label: 'WebFetch', description: 'Fetch URL content' },
  { type: 'tool', label: 'WebSearch', description: 'Search the web' },
  { type: 'tool', label: 'TodoWrite', description: 'Manage task list' },
  { type: 'tool', label: 'Question', description: 'Ask user a question' },
  { type: 'tool', label: 'Skill', description: 'Load a skill' },
  { type: 'tool', label: 'ApplyPatch', description: 'Apply a patch' },
];

interface AutocompletePopupProps {
  query: string;
  onSelect: (suggestion: Suggestion) => void;
  onClose: () => void;
}

export function AutocompletePopup({ query, onSelect, onClose }: AutocompletePopupProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const popupRef = useRef<HTMLDivElement>(null);

  const fetchSuggestions = useCallback(async (q: string) => {
    setLoading(true);
    try {
      const toolResults = KNOWN_TOOLS.filter((t) =>
        t.label.toLowerCase().includes(q.toLowerCase()),
      );

      let fileResults: Suggestion[] = [];
      if (q.length > 0) {
        const res = await fetch(`/api/files/search?q=${encodeURIComponent(q)}`);
        if (res.ok) {
          const files: string[] = await res.json();
          fileResults = files.slice(0, 10).map((f) => ({
            type: 'file' as const,
            label: f,
          }));
        }
      }

      const combined = [...toolResults, ...fileResults];
      setSuggestions(combined);
      setSelectedIndex(0);
    } catch {
      setSuggestions(KNOWN_TOOLS.filter((t) => t.label.toLowerCase().includes(q.toLowerCase())));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => fetchSuggestions(query), 150);
    return () => clearTimeout(timer);
  }, [query, fetchSuggestions]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((i) => Math.min(i + 1, suggestions.length - 1));
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((i) => Math.max(i - 1, 0));
          break;
        case 'Enter':
          e.preventDefault();
          if (suggestions[selectedIndex]) {
            onSelect(suggestions[selectedIndex]);
          }
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [suggestions, selectedIndex, onSelect, onClose]);

  if (suggestions.length === 0 && !loading) return null;

  return (
    <div
      ref={popupRef}
      className="absolute bottom-full left-0 right-0 mb-1 bg-v2-bg-deep border border-v2-border rounded-v2 shadow-lg max-h-48 overflow-y-auto z-50"
      role="listbox"
      aria-label="Suggestions"
    >
      {loading && (
        <div className="px-3 py-2 text-xs text-v2-text-muted">Searching...</div>
      )}
      {suggestions.map((s, i) => (
        <button
          key={`${s.type}-${s.label}`}
          role="option"
          aria-selected={i === selectedIndex}
          className={`w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors ${
            i === selectedIndex
              ? 'bg-v2-accent/10 text-v2-accent'
              : 'text-v2-text-secondary hover:bg-v2-bg-surface'
          }`}
          onClick={() => onSelect(s)}
          onMouseEnter={() => setSelectedIndex(i)}
        >
          <span className={`text-[10px] font-mono uppercase px-1 py-0.5 rounded ${
            s.type === 'tool'
              ? 'bg-blue-500/10 text-blue-400'
              : 'bg-green-500/10 text-green-400'
          }`}>
            {s.type}
          </span>
          <span className="font-medium">{s.label}</span>
          {s.description && (
            <span className="text-[10px] text-v2-text-muted ml-auto truncate">{s.description}</span>
          )}
        </button>
      ))}
    </div>
  );
}
