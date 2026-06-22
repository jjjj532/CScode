import { useEffect, useRef } from 'react';
import { Message } from './Message';
import { ThinkingIndicator } from './ThinkingIndicator';
import { ToolCallDisplay } from '../ui/ToolCallDisplay';
import { useSessionStore } from '../../stores/useSessionStore';

export function MessageList() {
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const sessionMessages = useSessionStore((s) => s.sessionMessages);
  const messages = sessionMessages[activeSessionId || ''] || [];
  const sessionLoading = useSessionStore((s) => s.sessionLoading);
  const sessionToolCalls = useSessionStore((s) => s.sessionToolCalls);
  const sessionThinking = useSessionStore((s) => s.sessionThinking);
  const endRef = useRef<HTMLDivElement>(null);

  const toolCalls = activeSessionId ? (sessionToolCalls[activeSessionId] || []) : [];
  const isThinking = activeSessionId ? (sessionThinking[activeSessionId] || false) : false;
  const isActiveProcessing = activeSessionId ? (sessionLoading[activeSessionId] || false) : false;
  const showProcessing = isActiveProcessing || isThinking || toolCalls.length > 0;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, toolCalls]);

  useEffect(() => {
    const total = messages.length;
    const userMsgs = messages.filter((m) => m.role === 'user').map((m) => JSON.stringify(m.content.slice(0, 30)));
    const userCount = messages.filter((m) => m.role === 'user').length;
    if (total > 0) {
      console.log('[MessageList] RENDER session=%s total=%d user=%d user_previews=%s', activeSessionId, total, userCount, JSON.stringify(userMsgs));
    }
    // Debug: log all session keys and their message counts every 5 renders
    const allKeys = Object.keys(sessionMessages);
    if (allKeys.length > 0 && total > 0) {
      const keyStats = allKeys.map(k => `${k.slice(0,8)}:${sessionMessages[k]?.length ?? 0}`).join(', ');
      console.log('[MessageList] sessionMessages keys: [%s] active=%s', keyStats, activeSessionId);
    }
  }, [messages, activeSessionId, sessionMessages]);

  if (messages.length === 0 && !showProcessing) {
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
      {messages.filter((msg) => msg.role !== 'system' && msg.role !== 'tool' && (msg.role !== 'assistant' || (msg.content && msg.content.trim()))).map((msg, idx) => (
        <Message key={msg.id || (msg.content ? msg.content.slice(0, 20) : `msg_${Math.random()}`)} message={msg} index={idx} />
      ))}
      {showProcessing && toolCalls.map((tc, i) => (
        <ToolCallDisplay key={`tc-${tc.name}-${i}`} {...tc} />
      ))}
      {showProcessing && toolCalls.length === 0 && <ThinkingIndicator />}
      <div ref={endRef} />
    </div>
  );
}
