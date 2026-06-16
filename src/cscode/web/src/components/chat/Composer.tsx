import { useState, useRef, useCallback } from 'react';
import { Paperclip, Send, Square, X } from 'lucide-react';
import { useChat } from '../../hooks/useChat';
import { useSessionStore } from '../../stores/useSessionStore';
import { useUIStore } from '../../stores/useUIStore';
import { useConfigStore } from '../../stores/useConfigStore';

export function Composer() {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage, stop } = useChat();
  const loading = useSessionStore((s) => s.loading);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const appendMessage = useSessionStore((s) => s.appendMessage);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const attachedFiles = useUIStore((s) => s.attachedFiles);
  const removeAttachedFile = useUIStore((s) => s.removeAttachedFile);
  const config = useConfigStore((s) => s.config);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    appendMessage({ role: 'user', content: text });

    try {
      const newSessionId = await sendMessage(text, activeSessionId || undefined);
      if (!activeSessionId && newSessionId) {
        setActiveSession(newSessionId);
      }
    } catch (err) {
      console.error('Chat error:', err);
      appendMessage({
        role: 'assistant',
        content: `Error: ${err instanceof Error ? err.message : 'Request failed'}`,
      });
    }
  }, [input, loading, activeSessionId, appendMessage, sendMessage, setActiveSession]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleAttachFile = async () => {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ multiple: true, title: 'Select files' });
      if (!selected) return;
      for (const path of Array.isArray(selected) ? selected : [selected]) {
        const file = new File([path], typeof path === 'string' ? path.split('/').pop() || path : 'file', { type: 'application/octet-stream' });
        useUIStore.getState().addAttachedFile(file);
      }
    } catch {
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.multiple = true;
      fileInput.onchange = () => {
        if (fileInput.files) {
          Array.from(fileInput.files).forEach((f) => useUIStore.getState().addAttachedFile(f));
        }
      };
      fileInput.click();
    }
  };

  return (
    <div className="border-t border-v2-border bg-v2-bg-base p-3">
      {attachedFiles.length > 0 && (
        <div className="flex gap-2 mb-2 flex-wrap">
          {attachedFiles.map((file, i) => (
            <span
              key={i}
              className="flex items-center gap-1 bg-v2-bg-surface text-xs text-v2-text-secondary px-2 py-1 rounded-md"
            >
              <Paperclip size={12} />
              {file.name}
              <button onClick={() => removeAttachedFile(i)} className="text-v2-text-muted hover:text-red-400">
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2 bg-v2-bg-deep border border-v2-border rounded-v2 px-3 py-2">
        <button onClick={handleAttachFile} className="text-v2-text-muted hover:text-v2-text-secondary transition-colors p-1">
          <Paperclip size={18} />
        </button>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything or @mention a file..."
          className="flex-1 bg-transparent text-sm text-v2-text-primary placeholder-v2-text-muted outline-none resize-none py-1 max-h-32"
          rows={1}
        />
        {loading ? (
          <button onClick={stop} className="bg-red-500 text-white p-2 rounded-lg hover:bg-red-600 transition-colors">
            <Square size={16} />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="bg-v2-accent text-white p-2 rounded-lg hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send size={16} />
          </button>
        )}
      </div>
      <div className="flex justify-between mt-1.5 px-1">
        <span className="text-[10px] text-v2-text-muted">
          Model: {config?.model || 'gpt-4o'} ({config?.provider || 'openai'})
        </span>
        <span className="text-[10px] text-v2-text-muted">
          @mention files · Tab to switch mode
        </span>
      </div>
    </div>
  );
}
