import { useState, useCallback } from 'react';
import { User, Sparkles, Copy, Check, RotateCcw } from 'lucide-react';
import { MarkdownRenderer } from '../markdown/MarkdownRenderer';
import type { Message as MessageType } from '../../stores/useSessionStore';
import { useSessionStore } from '../../stores/useSessionStore';
import { useConfigStore } from '../../stores/useConfigStore';

interface MessageProps {
  message: MessageType;
  index: number;
}

function formatTime(iso?: string): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${hh}:${mm}`;
  } catch {
    return '';
  }
}

export function Message({ message, index }: MessageProps) {
  const isUser = message.role === 'user';
  const config = useConfigStore((s) => s.config);
  const truncateMessages = useSessionStore((s) => s.truncateMessages);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const [copied, setCopied] = useState(false);

  const provider = config?.provider || 'openai';
  const model = config?.model || '';
  const time = formatTime(message.created_at);

  const footerParts = [provider, model, time].filter(Boolean);
  const footerText = footerParts.join(' · ');

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [message.content]);

  const handleReset = useCallback(() => {
    if (activeSessionId) {
      truncateMessages(activeSessionId, index);
    }
  }, [activeSessionId, index, truncateMessages]);

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-accent/20 flex items-center justify-center mt-1">
          <Sparkles size={16} className="text-v2-accent" />
        </div>
      )}
      <div className={`max-w-[75%] ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
        <div
          className={`rounded-v2 px-4 py-2.5 ${
            isUser
              ? 'bg-v2-msg-user border border-v2-border text-v2-text-primary'
              : 'bg-v2-msg-assistant border border-v2-border-light text-v2-text-primary'
          }`}
        >
          <div className={`text-xs font-medium mb-1 ${isUser ? 'text-v2-text-secondary' : 'text-v2-accent'}`}>
            {isUser ? 'You' : 'CScode'}
          </div>
          {isUser ? (
            <div className="text-sm whitespace-pre-wrap break-words leading-relaxed">{message.content}</div>
          ) : (
            <MarkdownRenderer content={message.content} />
          )}
        </div>
        <div className={`flex items-center gap-2 mt-1 px-1 ${isUser ? 'justify-end' : 'justify-start'}`}>
          <span className="text-[11px] text-v2-text-muted/60 select-none">{footerText}</span>
          {isUser && (
            <>
              <button
                onClick={handleReset}
                aria-label="重置到此点"
                className="text-[11px] text-v2-text-muted/60 hover:text-v2-accent transition-colors flex items-center gap-0.5"
                title="重置到此点"
              >
                <RotateCcw size={10} />
                <span>重置到此点</span>
              </button>
              <button
                onClick={handleCopy}
                aria-label="复制消息"
                className="text-[11px] text-v2-text-muted/60 hover:text-v2-accent transition-colors flex items-center gap-0.5"
                title="复制消息"
              >
                {copied ? <Check size={10} className="text-green-500" /> : <Copy size={10} />}
                <span>{copied ? '已复制' : '复制消息'}</span>
              </button>
            </>
          )}
        </div>
      </div>
      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-accent/20 flex items-center justify-center mt-1">
          <User size={16} className="text-v2-accent" />
        </div>
      )}
    </div>
  );
}
