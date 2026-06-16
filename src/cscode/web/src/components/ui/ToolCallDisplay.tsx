import { useState } from 'react';
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronRight, Terminal } from 'lucide-react';

interface ToolCallDisplayProps {
  name: string;
  round: number;
  max: number;
  success?: boolean;
  error?: string;
  output?: string;
}

export function ToolCallDisplay({ name, round, max, success, error, output }: ToolCallDisplayProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex gap-3 justify-start">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-bg-surface flex items-center justify-center">
        <Terminal size={16} className="text-v2-text-muted" />
      </div>
      <div className="bg-v2-msg-assistant border border-v2-border-light rounded-v2 min-w-[200px]">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 px-3 py-2 w-full text-left hover:bg-v2-bg-deep/50 transition-colors rounded-v2"
        >
          {success === undefined ? (
            <Loader2 size={14} className="text-v2-accent animate-spin" />
          ) : success ? (
            <CheckCircle2 size={14} className="text-v2-accent-secondary" />
          ) : (
            <XCircle size={14} className="text-red-400" />
          )}
          <span className="text-xs text-v2-text-secondary font-medium">{name}</span>
          <span className="text-[10px] text-v2-text-muted ml-auto">
            {round}/{max}
          </span>
          {output && (expanded ? <ChevronDown size={14} className="text-v2-text-muted" /> : <ChevronRight size={14} className="text-v2-text-muted" />)}
        </button>
        {expanded && output && (
          <pre className="px-3 pb-2 text-xs text-v2-text-secondary overflow-x-auto max-h-40">{output}</pre>
        )}
        {error && (
          <pre className="px-3 pb-2 text-xs text-red-400 overflow-x-auto">{error}</pre>
        )}
      </div>
    </div>
  );
}
