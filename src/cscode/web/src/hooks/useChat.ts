import { useRef, useCallback } from 'react';
import { useSessionStore } from '../stores/useSessionStore';

interface StreamEvent {
  type: string;
  session_id?: string;
  content?: string;
  name?: string;
  round?: number;
  max?: number;
  error?: string;
  stepLog?: string[];
}

type EventHandler = (event: StreamEvent) => void;

export function useChat() {
  const abortRef = useRef<AbortController | null>(null);
  const appendMessage = useSessionStore((s) => s.appendMessage);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const setLoading = useSessionStore((s) => s.setLoading);

  const sendMessage = useCallback(async (
    message: string,
    sessionId?: string,
    onThinking?: () => void,
    onToolStart?: (name: string, round: number, max: number) => void,
    onToolComplete?: (name: string, success: boolean) => void,
    onFileCreated?: (url: string) => void,
  ): Promise<string | undefined> => {
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);

    try {
      if (onThinking) onThinking();

      const params = new URLSearchParams({ message });
      if (sessionId) params.set('session_id', sessionId);

      const response = await fetch(`/api/chat/stream?${params}`, {
        method: 'POST',
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';
      let currentSessionId = sessionId;
      let assistantContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;

          try {
            const event: StreamEvent = JSON.parse(trimmed.slice(6));

            switch (event.type) {
              case 'session':
                if (event.session_id) {
                  currentSessionId = event.session_id;
                  setActiveSession(event.session_id);
                }
                break;
              case 'thinking':
                if (onThinking) onThinking();
                break;
              case 'tool:start':
                if (onToolStart) onToolStart(event.name || '', event.round || 0, event.max || 0);
                break;
              case 'tool:complete':
                if (onToolComplete) onToolComplete(event.name || '', true);
                break;
              case 'file_created':
                if (onFileCreated) onFileCreated(event.content || '');
                break;
              case 'complete':
                if (event.content) {
                  assistantContent = event.content;
                  appendMessage({ role: 'assistant', content: event.content });
                }
                break;
              case 'error':
                console.error('Stream error:', event.error);
                break;
            }
          } catch {
            // skip malformed JSON lines
          }
        }
      }

      return currentSessionId;
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        return sessionId;
      }
      throw err;
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }, [appendMessage, setActiveSession, setLoading]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setLoading(false);
  }, [setLoading]);

  return { sendMessage, stop };
}
