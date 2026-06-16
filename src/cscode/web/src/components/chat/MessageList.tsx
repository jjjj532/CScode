import { useEffect, useRef, useState } from 'react';
import { Message } from './Message';
import { ThinkingIndicator } from './ThinkingIndicator';
import { ToolCallDisplay } from '../ui/ToolCallDisplay';
import { useSessionStore } from '../../stores/useSessionStore';

interface ToolCallState {
  name: string;
  round: number;
  max: number;
  success?: boolean;
  error?: string;
  output?: string;
}

export function MessageList() {
  const messages = useSessionStore((s) => s.messages);
  const loading = useSessionStore((s) => s.loading);
  const endRef = useRef<HTMLDivElement>(null);
  const [toolCalls, setToolCalls] = useState<ToolCallState[]>([]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, toolCalls]);

  useEffect(() => {
    if (!loading) setToolCalls([]);
  }, [loading]);

  if (messages.length === 0 && !loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="text-4xl mb-4">🐚</div>
          <h2 className="text-xl font-semibold text-v2-text-primary mb-2">CScode</h2>
          <p className="text-sm text-v2-text-muted max-w-md">
            AI-powered coding assistant. Ask questions, write code, explore your codebase.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
      {messages.map((msg, i) => (
        <Message key={i} message={msg} />
      ))}
      {toolCalls.map((tc, i) => (
        <ToolCallDisplay key={i} {...tc} />
      ))}
      {loading && toolCalls.length === 0 && <ThinkingIndicator />}
      <div ref={endRef} />
    </div>
  );
}
