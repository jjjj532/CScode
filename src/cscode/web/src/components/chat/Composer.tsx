import { useState, useRef, useCallback } from 'react';
import { Paperclip, Send, Square, X, FileCode, FileImage, FileText } from 'lucide-react';
import { useChat } from '../../hooks/useChat';
import { useSessionStore } from '../../stores/useSessionStore';
import { useConfigStore } from '../../stores/useConfigStore';
import { useToastStore } from '../../stores/useToastStore';
import { AutocompletePopup } from '../ui/AutocompletePopup';
import { api } from '../../lib/api';

// Per-session sending guard — prevents the component-level useRef from
// blocking sends to a different session while another session's stream runs.
const sendingSessions: Record<string, boolean> = {};

export function Composer() {
  const [input, setInput] = useState('');
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage, stop } = useChat();
  const sessionLoading = useSessionStore((s) => s.sessionLoading);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const sessionAttachments = useSessionStore((s) => s.sessionAttachments);
  const addSessionAttachment = useSessionStore((s) => s.addSessionAttachment);
  const removeSessionAttachment = useSessionStore((s) => s.removeSessionAttachment);
  const clearSessionAttachments = useSessionStore((s) => s.clearSessionAttachments);
  const addSession = useSessionStore((s) => s.addSession);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const attachedFiles = activeSessionId ? (sessionAttachments[activeSessionId] || []) : [];
  const config = useConfigStore((s) => s.config);
  const addToast = useToastStore((s) => s.addToast);

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getFileIcon = (name: string) => {
    const ext = name.split('.').pop()?.toLowerCase();
    if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext || '')) return FileImage;
    if (['py', 'js', 'ts', 'tsx', 'jsx', 'java', 'c', 'cpp', 'go', 'rs'].includes(ext || '')) return FileCode;
    return FileText;
  };

  const extractMentionQuery = useCallback((value: string, cursorPos: number): string | null => {
    const beforeCursor = value.slice(0, cursorPos);
    const lastAtIndex = beforeCursor.lastIndexOf('@');
    if (lastAtIndex === -1) return null;
    const afterAt = beforeCursor.slice(lastAtIndex + 1);
    if (afterAt.includes(' ')) return null;
    return afterAt;
  }, []);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);
    const cursorPos = e.target.selectionStart ?? value.length;
    setMentionQuery(extractMentionQuery(value, cursorPos));
  }, [extractMentionQuery]);

  const handleMentionSelect = useCallback((suggestion: { type: string; label: string }) => {
    const pos = textareaRef.current?.selectionStart ?? input.length;
    const beforeCursor = input.slice(0, pos);
    const lastAtIndex = beforeCursor.lastIndexOf('@');
    if (lastAtIndex === -1) return;
    const before = input.slice(0, lastAtIndex);
    const after = input.slice(pos);
    const replacement = `@${suggestion.label} `;
    setInput(before + replacement + after);
    setMentionQuery(null);
    setTimeout(() => {
      const newPos = (before + replacement).length;
      textareaRef.current?.setSelectionRange(newPos, newPos);
      textareaRef.current?.focus();
    }, 0);
  }, [input]);

  const handleCloseMention = useCallback(() => {
    setMentionQuery(null);
  }, []);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    let sid = activeSessionId;
    const isSessionLoading = sid ? (sessionLoading[sid] || false) : false;
    if ((!text && attachedFiles.length === 0) || isSessionLoading) return;

    if (!sid) {
      try {
        const newSession = await api.sessions.create();
        addSession(newSession);
        setActiveSession(newSession.id);
        sid = newSession.id;
      } catch (err) {
        addToast('Failed to create session', 'error');
        console.error('Failed to create session:', err);
        return;
      }
    }

    // Per-session guard: don't allow concurrent sends to the same session
    if (sendingSessions[sid]) {
      console.log('[Composer] handleSend SKIPPED: session=%s already sending', sid);
      return;
    }
    sendingSessions[sid] = true;

    const filesToSend = attachedFiles.length > 0 ? [...attachedFiles] : undefined;

    setInput('');
    setMentionQuery(null);

    try {
      const returnedSid = await sendMessage(text, sid, filesToSend);
      if (filesToSend && returnedSid) clearSessionAttachments(returnedSid as string);
    } catch (err) {
      addToast('Chat error', 'error');
      console.error('Chat error:', err);
    } finally {
      sendingSessions[sid] = false;
    }
  }, [input, sessionLoading, activeSessionId, attachedFiles, sendMessage, clearSessionAttachments, addSession, setActiveSession]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (mentionQuery) {
      if (e.key === 'Escape') {
        e.preventDefault();
        setMentionQuery(null);
        return;
      }
      if (e.key === 'Enter' || e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() || attachedFiles.length > 0) handleSend();
    }
  };

  const handleAttachFile = async () => {
    let sid = activeSessionId;
    // Auto-create session if none exists, so files can be attached
    if (!sid) {
      try {
        const session = await api.sessions.create();
        addSession(session);
        setActiveSession(session.id);
        sid = session.id;
      } catch (e) {
        addToast('Failed to create session', 'error');
        console.error('Failed to create session for attachment', e);
        return;
      }
    }
    // 浏览器文件选择器——不需 Tauri fs 权限，macOS 不会弹授权窗
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.multiple = true;
    fileInput.onchange = () => {
      if (fileInput.files) {
        Array.from(fileInput.files).forEach((f) => useSessionStore.getState().addSessionAttachment(sid!, f));
      }
    };
    fileInput.click();
  };

  return (
    <div className="border-t border-v2-border bg-v2-bg-base p-3">
      {attachedFiles.length > 0 && (
        <div className="flex gap-2 mb-2 flex-wrap">
          {attachedFiles.map((file, i) => {
            const Icon = getFileIcon(file.name);
            return (
              <span
                key={i}
                className="flex items-center gap-1.5 bg-v2-bg-surface text-xs text-v2-text-secondary px-2 py-1 rounded-md"
              >
                <Icon size={12} className="text-v2-text-muted" />
                <span className="font-medium max-w-[120px] truncate" title={file.name}>{file.name}</span>
                <span className="text-v2-text-muted text-[10px]">{formatFileSize(file.size)}</span>
                <button onClick={() => activeSessionId && removeSessionAttachment(activeSessionId, i)} className="text-v2-text-muted hover:text-red-400">
                  <X size={12} />
                </button>
              </span>
            );
          })}
        </div>
      )}
      <div className="flex items-end gap-2 bg-v2-bg-deep border border-v2-border rounded-v2 px-3 py-2">
        <button onClick={handleAttachFile} className="text-v2-text-muted hover:text-v2-text-secondary transition-colors p-1">
          <Paperclip size={18} />
        </button>
        <div className="relative flex-1">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything or @mention a file..."
            className="w-full bg-transparent text-sm text-v2-text-primary placeholder-v2-text-muted outline-none resize-none py-1 max-h-32"
            rows={1}
          />
          {mentionQuery !== null && (
            <AutocompletePopup
              query={mentionQuery}
              onSelect={handleMentionSelect}
              onClose={handleCloseMention}
            />
          )}
        </div>
        {activeSessionId && sessionLoading[activeSessionId] ? (
          <button onClick={stop} className="bg-red-500 text-white p-2 rounded-lg hover:bg-red-600 transition-colors">
            <Square size={16} />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!input.trim() && attachedFiles.length === 0}
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
