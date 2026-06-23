import { useCallback } from 'react';
import { useSessionStore } from '../stores/useSessionStore';
import { api } from '../lib/api';

// Module-level shared abort controllers — all useChat() calls (Composer, Sidebar)
// share the same map, so abortSession from Sidebar actually aborts Composer's stream.
const streamControllers: Record<string, AbortController> = {};

interface FilePayload {
  name: string;
  content: string;
}

export function useChat() {
  const appendMessage = useSessionStore((s) => s.appendMessage);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const addSession = useSessionStore((s) => s.addSession);
  const setLoading = useSessionStore((s) => s.setLoading);
  const updateSessionTitle = useSessionStore((s) => s.updateSessionTitle);
  const setSessionThinking = useSessionStore((s) => s.setSessionThinking);
  const applyEvent = useSessionStore((s) => s.applyEvent);

  const readFileAsBase64 = (file: File): Promise<FilePayload> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        const base64 = result.split(',')[1] || result;
        resolve({ name: file.name, content: base64 });
      };
      reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
      reader.readAsDataURL(file);
    });
  };

  const abortSession = useCallback((sessionId: string) => {
    const ctrl = streamControllers[sessionId];
    if (ctrl) {
      console.log('[chat] abortSession: aborting stream for session=%s', sessionId);
      ctrl.abort();
      // Don't delete from map! Old controller stays so buffered events
      // can still pass isCurrent() check if no new stream replaces it.
      setLoading(sessionId, false);
      setSessionThinking(sessionId, false);
    }
  }, [setLoading, setSessionThinking]);

  const sendMessage = useCallback(async (
    message: string,
    sessionId?: string,
    files?: File[],
  ): Promise<string | undefined> => {
    const displayContent = files && files.length > 0
      ? message.trim()
        ? `${message}\n\n[Files: ${files.map(f => f.name).join(', ')}]`
        : `[Files: ${files.map(f => f.name).join(', ')}]`
      : message;

    // Follow opencode pattern: create session FIRST, then send message.
    let sid = sessionId;
    if (!sid) {
      try {
        const session = await api.sessions.create();
        addSession(session);
        setActiveSession(session.id);
        sid = session.id;
      } catch (e) {
        console.error('Failed to create session', e);
        return undefined;
      }
    }

    // Abort any existing stream for this session before starting a new one
    abortSession(sid);

    const controller = new AbortController();
    streamControllers[sid] = controller;

    // Now sid is always known. Add user message to the correct session.
    setSessionThinking(sid, false);
    console.log('[chat] sendMessage: appending user message sid=%s content_preview=%s', sid, JSON.stringify(displayContent.slice(0, 60)));
    appendMessage({ role: 'user', content: displayContent, created_at: new Date().toISOString() }, sid);
    console.log('[chat] sendMessage: setLoading(true) sid=%s', sid);
    setLoading(sid, true);

    let intentionalAbort = false;

    try {
      const body: Record<string, unknown> = { message, session_id: sid };
      if (files && files.length > 0) {
        const filePayloads = await Promise.all(files.map(readFileAsBase64));
        body.files = filePayloads;
      }

      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';
      let lastChunkTime = Date.now();
      let intentionalAbort = false;

      while (true) {
        if (Date.now() - lastChunkTime > 300_000) {
          controller.abort();
          throw new Error('Stream timed out: no data for 5min');
        }
        const readPromise = reader.read();
        const readTimeout = new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error('Read timeout')), 300_000)
        );
        const { done, value } = await Promise.race([readPromise, readTimeout]);
        if (done) break;
        lastChunkTime = Date.now();

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;

          try {
            const event = JSON.parse(trimmed.slice(6));
            const isCurrent = () => {
              const activeId = useSessionStore.getState().activeSessionId;
              return streamControllers[sid] === controller && activeId === sid;
            };

            switch (event.type) {
              case 'session':
                break;
              case 'session:title':
                if (isCurrent() && event.title) {
                  updateSessionTitle(sid, event.title);
                }
                break;
              case 'step.started':
              case 'text.ended':
              case 'tool.called':
              case 'tool.success':
              case 'tool.failed':
              case 'step.ended':
                if (isCurrent()) {
                  applyEvent(sid, event);
                }
                break;
              case 'status':
                if (isCurrent()) {
                  setSessionThinking(sid, true);
                }
                break;
              case 'file_created':
                break;
              case 'complete':
                setSessionThinking(sid, false);
                if (isCurrent()) {
                  setLoading(sid, false);
                  if (event.content) {
                    const store = useSessionStore.getState();
                    const msgs = store.sessionMessages[sid] || [];
                    const lastMsg = msgs[msgs.length - 1];
                    if (lastMsg?.role === 'assistant' && lastMsg.content === event.content) {
                      break;
                    }
                    appendMessage({ role: 'assistant', content: event.content }, sid);
                  }
                }
                break;
              case 'error':
                if (isCurrent()) {
                  setSessionThinking(sid, false);
                  setLoading(sid, false);
                  appendMessage({
                    role: 'assistant',
                    content: `Error: ${event.content || event.error || 'Unknown error'}`,
                  }, sid);
                }
                break;
            }
          } catch {
            // skip malformed JSON lines
          }
        }
      }

      console.log('[chat] stream ended normally for session=%s', sid);
      return sid;
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        intentionalAbort = true;
        console.log('[chat] stream ABORTED for session=%s', sid);
        return sid;
      }
      const stillCurrent = streamControllers[sid] === controller;
      if (stillCurrent) {
        appendMessage({
          role: 'assistant',
          content: `Error: ${err instanceof Error ? err.message : 'Request failed'}`,
        }, sid);
      } else {
        console.log('[chat] error event DROPPED for session=%s (stale stream): %s', sid, err instanceof Error ? err.message : 'unknown');
      }
      throw err;
    } finally {
      if (streamControllers[sid] === controller) {
        delete streamControllers[sid];
        if (!intentionalAbort) {
          setSessionThinking(sid, false);
          setLoading(sid, false);
        }
      } else {
        console.log('[chat] stream finally: controller superseded for session=%s (another stream started)', sid);
      }
    }
  }, [appendMessage, setActiveSession, addSession, setLoading, updateSessionTitle, setSessionThinking, applyEvent, abortSession]);

  const stop = useCallback(() => {
    // Only abort the active session's stream
    const sid = useSessionStore.getState().activeSessionId;
    if (sid) {
      const ctrl = streamControllers[sid];
      if (ctrl) {
        console.log('[chat] stop: aborting stream for active session=%s', sid);
        ctrl.abort();
        // Don't delete from map — same reason as abortSession
        setLoading(sid, false);
        setSessionThinking(sid, false);
      }
    }
  }, [setLoading, setSessionThinking]);

  return { sendMessage, stop, abortSession };
}
