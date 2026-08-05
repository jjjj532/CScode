import { useCallback } from 'react';
import { useSessionStore } from '../stores/useSessionStore';
import { useToastStore } from '../stores/useToastStore';
import { api } from '../lib/api';

const streamControllers: Record<string, AbortController> = {};
// Prevent concurrent streams for the same session
const activeStreams = new Set<string>();
// Per-session send cooldown: blocks duplicate sends within 1s (double-stream guard)
const lastSendAt: Record<string, number> = {};
const SEND_COOLDOWN_MS = 1000;

export function __resetSendCooldownForTests(): void {
  for (const k of Object.keys(lastSendAt)) {
    delete lastSendAt[k];
  }
}

export function abortSession(sessionId: string) {
  const ctrl = streamControllers[sessionId];
  if (ctrl) {
    console.log('[chat] abortSession: aborting stream for session=%s', sessionId);
    ctrl.abort();
    delete streamControllers[sessionId];
    activeStreams.delete(sessionId);
    // Reset session state immediately so it doesn't show "Thinking..." when user returns
    useSessionStore.getState().setSessionThinking(sessionId, false);
    useSessionStore.getState().setLoading(sessionId, false);
  }
}

export function isSessionStreaming(sessionId: string): boolean {
  return activeStreams.has(sessionId);
}

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

    let sid = sessionId;
    if (!sid) {
      // Guard: if sidebar is creating a new session (activeSessionId === null), don't create duplicate
      const currentActive = useSessionStore.getState().activeSessionId;
      if (currentActive === null) {
        return undefined;
      }
      try {
        const session = await api.session.create();
        addSession(session);
        setActiveSession(session.id);
        sid = session.id;
      } catch (e) {
        useToastStore.getState().addToast('Failed to create session', 'error');
        console.error('Failed to create session', e);
        return undefined;
      }
    }

    if (activeStreams.has(sid)) {
      useToastStore.getState().addToast('Session is already generating a response', 'warning');
      return undefined;
    }

    const now = Date.now();
    if (lastSendAt[sid] && now - lastSendAt[sid] < SEND_COOLDOWN_MS) {
      useToastStore.getState().addToast('发送太快，请稍候再试', 'warning');
      return undefined;
    }
    lastSendAt[sid] = now;

    abortSession(sid);

    const capturedSid = sid;
    const controller = new AbortController();
    streamControllers[capturedSid] = controller;
    activeStreams.add(capturedSid);

    setSessionThinking(sid, false);
    console.log('[chat] sendMessage: appending user message sid=%s content_preview=%s', sid, JSON.stringify(displayContent.slice(0, 60)));
    appendMessage({ role: 'user', content: displayContent, created_at: new Date().toISOString() }, sid);
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

      while (true) {
        const { done, value } = await reader.read();
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

            // Architecture root fix: filter events by session_id
            // This prevents stale events from a different session polluting this stream
            if (event.session_id && event.session_id !== capturedSid) {
              console.log('[chat] DROPPED event for wrong session: event_session=%s current=%s type=%s', event.session_id, capturedSid, event.type);
              continue;
            }

            const isCurrentStream = () => {
              return streamControllers[capturedSid] === controller;
            };

            // Extract data from both {type, data} format (P0-5 fix) and legacy top-level format
            const d = (event as any).data || event;

            switch (event.type) {
              case 'session':
                break;
              case 'session:title':
                if (isCurrentStream() && (d.title || event.title)) {
                  updateSessionTitle(capturedSid, d.title || event.title);
                }
                break;
              case 'text.delta':
              case 'step.started':
              case 'text.ended':
              case 'tool.called':
              case 'tool.success':
              case 'tool.failed':
              case 'step.ended':
                if (isCurrentStream()) {
                  applyEvent(capturedSid, event);
                }
                break;
              case 'status':
                if (isCurrentStream()) {
                  setSessionThinking(capturedSid, true);
                }
                break;
              case 'file_created': {
                const filename = d.filename || (event as any).filename;
                if (filename && isCurrentStream()) {
                  useSessionStore.getState().addSessionFile(capturedSid, filename);
                }
                break;
              }
              case 'complete':
                if (isCurrentStream()) {
                  setSessionThinking(capturedSid, false);
                  setLoading(capturedSid, false);
                  const content = d.content || (event as any).content;
                  if (content) {
                    const store = useSessionStore.getState();
                    const msgs = store.sessionMessages[capturedSid] || [];
                    const lastMsg = msgs[msgs.length - 1];
                    if (lastMsg?.role === 'assistant' && lastMsg.content === content) {
                      break;
                    }
                    appendMessage({ role: 'assistant', content }, capturedSid);
                  }
                }
                break;
              case 'error':
                if (isCurrentStream()) {
                  setSessionThinking(capturedSid, false);
                  setLoading(capturedSid, false);
                  appendMessage({
                    role: 'assistant',
                    content: `Error: ${d.content || (event as any).content || d.error || (event as any).error || 'Unknown error'}`,
                  }, capturedSid);
                }
                break;
            }
          } catch {
            // skip malformed JSON lines
          }
        }
      }

      console.log('[chat] stream ended normally for session=%s', capturedSid);
      return capturedSid;
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        intentionalAbort = true;
        console.log('[chat] stream ABORTED for session=%s', capturedSid);
        return capturedSid;
      }
      const stillCurrent = streamControllers[capturedSid] === controller;
      if (stillCurrent) {
        appendMessage({
          role: 'assistant',
          content: `Error: ${err instanceof Error ? err.message : 'Request failed'}`,
        }, capturedSid);
      } else {
        console.log('[chat] error event DROPPED for session=%s (stale stream): %s', capturedSid, err instanceof Error ? err.message : 'unknown');
      }
      throw err;
    } finally {
      if (streamControllers[capturedSid] === controller) {
        delete streamControllers[capturedSid];
        activeStreams.delete(capturedSid);
        if (!intentionalAbort) {
          setSessionThinking(capturedSid, false);
          setLoading(capturedSid, false);
        }
      } else {
        activeStreams.delete(capturedSid);
        console.log('[chat] stream finally: controller superseded for session=%s (another stream started)', capturedSid);
      }
    }
  }, [appendMessage, setActiveSession, addSession, setLoading, updateSessionTitle, setSessionThinking, applyEvent]);

  const stop = useCallback(() => {
    const sid = useSessionStore.getState().activeSessionId;
    if (sid) {
      // Architecture root fix: stop via backend API, not just aborting the fetch
      // This ensures the backend agent task is actually cancelled
      fetch(`/api/sessions/${sid}/stop`, { method: 'POST' }).catch((e) => {
        useToastStore.getState().addToast('Failed to stop session', 'error');
        console.error('[chat] stop: backend stop failed', e);
      });
      // Also abort the frontend stream controller
      const ctrl = streamControllers[sid];
      if (ctrl) {
        ctrl.abort();
        delete streamControllers[sid];
      }
      setLoading(sid, false);
      setSessionThinking(sid, false);
    }
  }, [setLoading, setSessionThinking]);

  return { sendMessage, stop, abortSession };
}
