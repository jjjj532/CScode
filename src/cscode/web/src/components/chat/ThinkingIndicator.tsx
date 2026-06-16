import { Sparkles } from 'lucide-react';

export function ThinkingIndicator() {
  return (
    <div className="flex gap-3 justify-start">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-accent/20 flex items-center justify-center">
        <Sparkles size={16} className="text-v2-accent" />
      </div>
      <div className="bg-v2-msg-assistant border border-v2-border-light rounded-v2 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            <span className="w-2 h-2 bg-v2-accent rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-2 h-2 bg-v2-accent rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-2 h-2 bg-v2-accent rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
          <span className="text-xs text-v2-text-muted">Thinking...</span>
        </div>
      </div>
    </div>
  );
}
