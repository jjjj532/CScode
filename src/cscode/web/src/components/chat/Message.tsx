import { User, Sparkles } from 'lucide-react';
import { MarkdownRenderer } from '../markdown/MarkdownRenderer';
import type { Message as MessageType } from '../../stores/useSessionStore';

interface MessageProps {
  message: MessageType;
}

export function Message({ message }: MessageProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-accent/20 flex items-center justify-center">
          <Sparkles size={16} className="text-v2-accent" />
        </div>
      )}
      <div
        className={`max-w-[75%] rounded-v2 px-4 py-2.5 ${
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
      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-accent/20 flex items-center justify-center">
          <User size={16} className="text-v2-accent" />
        </div>
      )}
    </div>
  );
}
