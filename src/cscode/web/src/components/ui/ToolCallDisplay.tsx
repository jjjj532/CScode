import { useState } from 'react';
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronRight, Terminal, Clock } from 'lucide-react';

interface ToolCallDisplayProps {
  name: string;
  args?: string;
  round: number;
  max: number;
  status: 'pending' | 'running' | 'success' | 'error';
  error?: string;
  output?: string;
  stepLog: string[];
}

export function ToolCallDisplay({ name, args, round, max, status, error, output, stepLog }: ToolCallDisplayProps) {
  const [expanded, setExpanded] = useState(true);

  const statusIcon = () => {
    switch (status) {
      case 'pending':
        return <Clock size={14} className="text-v2-text-muted" />;
      case 'running':
        return <Loader2 size={14} className="text-v2-accent animate-spin" />;
      case 'success':
        return <CheckCircle2 size={14} className="text-v2-accent-secondary" />;
      case 'error':
        return <XCircle size={14} className="text-red-400" />;
    }
  };

  const hasDetail = !!(output || error || stepLog.length > 0 || args);

  const briefLabel = (() => {
    if (!args) return name;
    try {
      const parsed = JSON.parse(args);
      const filePath = parsed.file_path || parsed.path || parsed.filePath || parsed.pattern || '';
      if (filePath) return `${name} ${filePath}`;
      const keys = Object.keys(parsed);
      if (keys.length === 1) return `${name} ${String(parsed[keys[0]]).slice(0, 40)}`;
      return `${name} (${keys.length} args)`;
    } catch {
      return `${name} ${args.slice(0, 40)}`;
    }
  })();

  const formattedArgs = (() => {
    if (!args) return null;
    try {
      return JSON.stringify(JSON.parse(args), null, 2);
    } catch {
      return args;
    }
  })();

  return (
    <div className="flex gap-3 justify-start" role="status" aria-live="polite" aria-label={`Tool: ${name}`}>
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-bg-surface flex items-center justify-center">
        <Terminal size={16} className="text-v2-text-muted" />
      </div>
      <div className="bg-v2-msg-assistant border border-v2-border-light rounded-v2 min-w-[200px] max-w-xl flex-1">
        <button
          onClick={() => setExpanded(!expanded)}
          aria-label={expanded ? 'Collapse tool call' : 'Expand tool call'}
          className="flex items-center gap-2 px-3 py-2 w-full text-left hover:bg-v2-bg-deep/50 transition-colors rounded-v2"
        >
          {statusIcon()}
          <span className="text-xs text-v2-text-secondary font-medium truncate">{briefLabel}</span>
          <span className="text-[10px] text-v2-text-muted ml-auto shrink-0">{round}/{max}</span>
          {hasDetail && (expanded ? <ChevronDown size={14} className="text-v2-text-muted shrink-0" /> : <ChevronRight size={14} className="text-v2-text-muted shrink-0" />)}
        </button>
        {expanded && (
          <div className="px-3 pb-2 space-y-1 border-t border-v2-border-light pt-1.5">
            {formattedArgs && (
              <pre className="text-xs text-v2-text-muted overflow-x-auto max-h-32 whitespace-pre-wrap">{formattedArgs}</pre>
            )}
            {stepLog.length > 0 && (
              <div className="space-y-0.5">
                {stepLog.map((step, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-xs text-v2-text-muted">
                    <span className="text-v2-accent-secondary mt-px">▸</span>
                    <span>{step}</span>
                  </div>
                ))}
              </div>
            )}
            {output && (
              <pre className="text-xs text-v2-text-secondary overflow-x-auto max-h-40">{output}</pre>
            )}
            {error && (
              <pre className="text-xs text-red-400 overflow-x-auto">{error}</pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
