import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Session {
  id: string;
  title: string;
  provider?: string;
  model?: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id?: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  created_at?: string;
}

export interface ToolCallItem {
  name: string;
  args?: string;
  round: number;
  max: number;
  status: 'pending' | 'running' | 'success' | 'error';
  output?: string;
  error?: string;
  stepLog: string[];
}

const pollingTimers: Record<string, ReturnType<typeof setInterval>> = {};

function pollQuestionRequestId(sessionId: string, questionText: string) {
  const key = `${sessionId}:${questionText}`;
  if (pollingTimers[key]) return;
  pollingTimers[key] = setInterval(async () => {
    try {
      const res = await fetch(`/api/sessions/${sessionId}/questions`);
      if (!res.ok) return;
      // Backend returns: [{ request_id, session_id, tool_call_id, questions: [{question, options}] }]
      const entries: Array<{ request_id: string; questions: Array<{ question: string; options: string[] }> }> = await res.json();
      for (const entry of entries) {
        if (entry.request_id === '__polling__' || !entry.questions) continue;
        for (const q of entry.questions) {
          if (q.question === questionText && entry.request_id !== '__polling__') {
            clearInterval(pollingTimers[key]);
            delete pollingTimers[key];
            // Use the proper store action to trigger React re-render
            useSessionStore.getState().updatePendingQuestionRequestId(sessionId, questionText, entry.request_id);
            return;
          }
        }
      }
    } catch {
      // ignore polling errors
    }
  }, 500);
  setTimeout(() => {
    clearInterval(pollingTimers[key]);
    delete pollingTimers[key];
  }, 30000);
}

function toolSummary(tc: ToolCallItem): string {
  const icon = tc.status === 'success' ? '✅' : tc.status === 'error' ? '❌' : '🔄';
  let desc = tc.name;
  if (tc.args) {
    try {
      const args = JSON.parse(tc.args);
      switch (tc.name) {
        case 'browser': {
          const a = args.action || '';
          if (a === 'open') desc += ` 打开 ${args.url || ''}`;
          else if (a === 'click') desc += ` 点击 ${args.selector || ''}`;
          else if (a === 'type') desc += ` 输入 ${(args.text || '').slice(0, 30)}`;
          else if (a === 'press') desc += ` 按键 ${args.key || ''}`;
          else if (a === 'screenshot') desc += ` 截图`;
          else if (a === 'get_text') desc += ` 获取文本 ${args.selector || ''}`;
          else if (a === 'get_html') desc += ` 获取HTML ${args.selector || ''}`;
          else if (a === 'wait') desc += ` 等待 ${args.selector || ''}`;
          else if (a === 'scroll') desc += ` 滚动到 ${args.selector || ''}`;
          else if (a === 'close') desc += ` 关闭浏览器`;
          else desc += ` ${a}`;
          break;
        }
        case 'bash': {
          const cmd = (args.command || '').slice(0, 100);
          desc += ` ${cmd}${cmd.length >= 100 ? '...' : ''}`;
          break;
        }
        case 'read': desc += ` ${args.file_path || args.path || ''}`; break;
        case 'write': desc += ` ${args.file_path || args.path || ''}`; break;
        case 'edit': desc += ` ${args.file_path || args.path || ''}`; break;
        case 'grep': desc += ` ${args.pattern || ''}`; break;
        case 'glob': desc += ` ${args.pattern || ''}`; break;
        case 'ls': desc += ` ${args.path || ''}`; break;
        case 'webfetch': desc += ` ${args.url || ''}`; break;
        case 'websearch': desc += ` ${(args.query || '').slice(0, 60)}`; break;
        default:
          const raw = JSON.stringify(args).slice(0, 60);
          desc += ` ${raw}${raw.length >= 60 ? '...' : ''}`;
      }
    } catch {
      desc += ` ${tc.args.slice(0, 80)}`;
    }
  }
  return `${icon} ${desc}`;
}

export interface QuestionItem {
  request_id: string;
  question: string;
  options: string[];
}

interface SessionState {
  sessions: Session[];
  sessionMessages: Record<string, Message[]>;
  sessionMessageVersion: Record<string, number>;
  activeSessionId: string | null;
  sessionLoading: Record<string, boolean>;
  sessionToolCalls: Record<string, ToolCallItem[]>;
  sessionThinking: Record<string, boolean>;
  sessionAttachments: Record<string, File[]>;
  sessionLastSeq: Record<string, number>;
  pendingQuestions: Record<string, QuestionItem[]>;
  setSessions: (sessions: Session[]) => void;
  setMessages: (messages: Message[], sessionId: string) => void;
  applyEvent: (sessionId: string, event: { type: string; data?: any }) => void;
  setSessionLastSeq: (sessionId: string, seq: number) => void;
  appendMessage: (message: Message, sessionId: string) => void;
  setActiveSession: (id: string | null) => void;
  setLoading: (sessionId: string, loading: boolean) => void;
  addSession: (session: Session) => void;
  removeSession: (id: string) => void;
  updateSessionTitle: (id: string, title: string) => void;
  addToolCall: (sessionId: string, call: ToolCallItem) => void;
  updateToolCall: (sessionId: string, name: string, updates: Partial<ToolCallItem>) => void;
  appendToolCallStep: (sessionId: string, name: string, step: string) => void;
  clearSessionToolCalls: (sessionId: string) => void;
  setSessionThinking: (sessionId: string, thinking: boolean) => void;
  setSessionAttachments: (sessionId: string, files: File[]) => void;
  addSessionAttachment: (sessionId: string, file: File) => void;
  removeSessionAttachment: (sessionId: string, index: number) => void;
  clearSessionAttachments: (sessionId: string) => void;
  truncateMessages: (sessionId: string, toIndex: number) => void;
  dismissQuestion: (sessionId: string) => void;
  updatePendingQuestionRequestId: (sessionId: string, questionText: string, requestId: string) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  sessionMessages: {},
  sessionMessageVersion: {},
  activeSessionId: null,
  sessionLoading: {},
  sessionToolCalls: {},
  sessionThinking: {},
  sessionAttachments: {},
  sessionLastSeq: {},
  pendingQuestions: {},
  setSessions: (sessions) => set({ sessions }),
  setSessionLastSeq: (sessionId, seq) => set((s) => ({
    sessionLastSeq: { ...s.sessionLastSeq, [sessionId]: seq },
  })),
  applyEvent: (sessionId, event) => set((s) => {
    const d = event.data;
    const bumpVersion = () => {
      const newVer = (s.sessionMessageVersion[sessionId] || 0) + 1;
      return { sessionMessageVersion: { ...s.sessionMessageVersion, [sessionId]: newVer } };
    };
    switch (event.type) {
      case 'text.delta': {
        const content = d?.content || '';
        if (!content) return s;
        const msgs = s.sessionMessages[sessionId] || [];
        const lastIdx = msgs.length - 1;
        // Append delta content to the last assistant message (streaming typewriter effect)
        if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
          const updated = [...msgs];
          updated[lastIdx] = { ...updated[lastIdx], content: updated[lastIdx].content + content };
          return {
            ...bumpVersion(),
            sessionThinking: { ...s.sessionThinking, [sessionId]: true },
            sessionMessages: { ...s.sessionMessages, [sessionId]: updated },
          };
        }
        // No existing assistant message — create one
        return {
          ...bumpVersion(),
          sessionThinking: { ...s.sessionThinking, [sessionId]: true },
          sessionMessages: {
            ...s.sessionMessages,
            [sessionId]: [
              ...msgs,
              { role: 'assistant' as const, content, created_at: new Date().toISOString() },
            ],
          },
        };
      }
      case 'step.started': {
        const msgs = s.sessionMessages[sessionId] || [];
        // Only add placeholder if last message isn't already an empty assistant message
        const last = msgs[msgs.length - 1];
        if (last?.role === 'assistant' && !last.content?.trim()) {
          return {
            ...bumpVersion(),
            sessionThinking: { ...s.sessionThinking, [sessionId]: true },
            sessionToolCalls: { ...s.sessionToolCalls, [sessionId]: [] },
          };
        }
        return {
          ...bumpVersion(),
          sessionThinking: { ...s.sessionThinking, [sessionId]: true },
          sessionToolCalls: { ...s.sessionToolCalls, [sessionId]: [] },
          sessionMessages: {
            ...s.sessionMessages,
            [sessionId]: [
              ...msgs,
              { role: 'assistant' as const, content: '', created_at: new Date().toISOString() },
            ],
          },
        };
      }
      case 'text.ended': {
        const content = d?.content;
        if (!content?.trim()) return s;
        const msgs = s.sessionMessages[sessionId] || [];
        // Update the last assistant message instead of appending
        const lastIdx = msgs.length - 1;
        if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
          const updated = [...msgs];
          updated[lastIdx] = { ...updated[lastIdx], content };
          return {
            ...bumpVersion(),
            sessionThinking: { ...s.sessionThinking, [sessionId]: false },
            sessionMessages: { ...s.sessionMessages, [sessionId]: updated },
          };
        }
        // Fallback: append new message
        return {
          ...bumpVersion(),
          sessionThinking: { ...s.sessionThinking, [sessionId]: false },
          sessionMessages: {
            ...s.sessionMessages,
            [sessionId]: [...msgs, { role: 'assistant' as const, content, created_at: new Date().toISOString() }],
          },
        };
      }
      case 'tool.called': {
        const argsStr = d?.args ? (typeof d.args === 'object' ? JSON.stringify(d.args) : String(d.args)) : '';
        const name = d?.name || '';
        const result: Partial<SessionState> = {
          sessionThinking: { ...s.sessionThinking, [sessionId]: false },
          sessionToolCalls: {
            ...s.sessionToolCalls,
            [sessionId]: [
              ...(s.sessionToolCalls[sessionId] || []),
              { name, args: argsStr, status: 'running' as const, round: d?.round || 0, max: d?.max || 0, stepLog: [] },
            ],
          },
        };
        // If this is a question tool call, trigger polling for pending question details
        if (name === 'question' && d?.args?.question) {
          const questions = s.pendingQuestions[sessionId] || [];
          const questionItem: QuestionItem = {
            request_id: '__polling__',
            question: d.args.question || '',
            options: d.args.options || [],
          };
          // Only add if we don't already have this question pending
          if (!questions.some((q) => q.question === questionItem.question)) {
            result.pendingQuestions = {
              ...s.pendingQuestions,
              [sessionId]: [...questions, questionItem],
            };
          }
          // Start polling for the real request_id (fire-and-forget)
          pollQuestionRequestId(sessionId, questionItem.question);
        }
        return result as SessionState;
      }
      case 'tool.success':
        return {
          sessionToolCalls: {
            ...s.sessionToolCalls,
            [sessionId]: (s.sessionToolCalls[sessionId] || []).map((tc) =>
              tc.name === d?.name && tc.status === 'running' ? { ...tc, status: 'success' as const, output: d?.result } : tc
            ),
          },
        };
      case 'tool.failed':
        return {
          sessionToolCalls: {
            ...s.sessionToolCalls,
            [sessionId]: (s.sessionToolCalls[sessionId] || []).map((tc) =>
              tc.name === d?.name && tc.status === 'running' ? { ...tc, status: 'error' as const, error: d?.error } : tc
            ),
          },
        };
      case 'step.ended': {
        const tcList = s.sessionToolCalls[sessionId] || [];
        if (tcList.length > 0) {
          const summary = tcList.map(toolSummary).join('\n');
          const round = d?.round || '?';
          const summaryMsg = `**步骤 ${round} 执行摘要：**\n${summary}`;
          return {
            ...bumpVersion(),
            sessionThinking: { ...s.sessionThinking, [sessionId]: false },
            sessionMessages: {
              ...s.sessionMessages,
              [sessionId]: [
                ...(s.sessionMessages[sessionId] || []),
                { role: 'assistant' as const, content: summaryMsg, created_at: new Date().toISOString() },
              ],
            },
          };
        }
        return { ...bumpVersion(), sessionThinking: { ...s.sessionThinking, [sessionId]: false } };
      }
      default:
        return s;
    }
  }),
  appendMessage: (message, sessionId) => set((s) => {
    // Drop empty assistant messages at the store level
    if (message.role === 'assistant' && !message.content?.trim()) {
      console.log('[store] appendMessage DROPPED empty assistant message for session=%s', sessionId);
      return s;
    }
    const current = s.sessionMessages[sessionId] || [];
    const newMsg = {
      ...message,
      id: message.id || `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      created_at: message.created_at || new Date().toISOString(),
    };
    const newVersion = (s.sessionMessageVersion[sessionId] || 0) + 1;
    console.log('[store] appendMessage role=%s content_preview=%s session=%s total=%d version=%d', message.role, JSON.stringify((message.content || '').slice(0, 40)), sessionId, current.length + 1, newVersion);
    return {
      sessionMessages: {
        ...s.sessionMessages,
        [sessionId]: [...current, newMsg],
      },
      sessionMessageVersion: {
        ...s.sessionMessageVersion,
        [sessionId]: newVersion,
      },
    };
  }),
  setMessages: (messages, sessionId) => set((s) => {
    const prev = s.sessionMessages[sessionId];
    const filtered = messages.filter(
      (m) => m.role !== 'assistant' || (m.content && m.content.trim())
    );
    console.log('[store] setMessages session=%s prev=%d -> fetched=%d filtered=%d', sessionId, prev?.length || 0, messages.length, filtered.length);
    if (filtered.length !== messages.length) {
      console.log('[store] setMessages filtered %d empty assistant messages for session=%s', messages.length - filtered.length, sessionId);
    }
    return {
      sessionMessages: {
        ...s.sessionMessages,
        [sessionId]: filtered,
      },
    };
  }),
  setActiveSession: (id) => set({ activeSessionId: id }),
  setLoading: (sessionId, loading) => set((s) => ({
    sessionLoading: { ...s.sessionLoading, [sessionId]: loading },
  })),
  addSession: (session) => set((s) => ({ sessions: [...s.sessions, session] })),
  removeSession: (id) => set((s) => {
    const { [id]: msgs, ...rest } = s.sessionMessages;
    const { [id]: ver, ...restVer } = s.sessionMessageVersion;
    const { [id]: tcs, ...restTc } = s.sessionToolCalls;
    const { [id]: th, ...restTh } = s.sessionThinking;
    const { [id]: att, ...restAtt } = s.sessionAttachments;
    const { [id]: ld, ...restLd } = s.sessionLoading;
    const { [id]: seq, ...restSeq } = s.sessionLastSeq;
    return {
      sessions: s.sessions.filter((x) => x.id !== id),
      sessionMessages: rest,
      sessionMessageVersion: restVer,
      sessionToolCalls: restTc,
      sessionThinking: restTh,
      sessionAttachments: restAtt,
      sessionLoading: restLd,
      sessionLastSeq: restSeq,
    };
  }),
  updateSessionTitle: (id, title) => set((s) => ({
    sessions: s.sessions.map((x) => x.id === id ? { ...x, title } : x),
  })),
  addToolCall: (sessionId, call) => set((s) => ({
    sessionToolCalls: {
      ...s.sessionToolCalls,
      [sessionId]: [...(s.sessionToolCalls[sessionId] || []), call],
    },
  })),
  updateToolCall: (sessionId, name, updates) => set((s) => ({
    sessionToolCalls: {
      ...s.sessionToolCalls,
      [sessionId]: (s.sessionToolCalls[sessionId] || []).map((tc) =>
        tc.name === name ? { ...tc, ...updates } : tc
      ),
    },
  })),
  appendToolCallStep: (sessionId, name, step) => set((s) => ({
    sessionToolCalls: {
      ...s.sessionToolCalls,
      [sessionId]: (s.sessionToolCalls[sessionId] || []).map((tc) =>
        tc.name === name ? { ...tc, stepLog: [...(tc.stepLog || []), step] } : tc
      ),
    },
  })),
  clearSessionToolCalls: (sessionId) => set((s) => ({
    sessionToolCalls: { ...s.sessionToolCalls, [sessionId]: [] },
  })),
  setSessionThinking: (sessionId, thinking) => set((s) => ({
    sessionThinking: { ...s.sessionThinking, [sessionId]: thinking },
  })),
  setSessionAttachments: (sessionId, files) => set((s) => ({
    sessionAttachments: { ...s.sessionAttachments, [sessionId]: files },
  })),
  addSessionAttachment: (sessionId, file) => set((s) => ({
    sessionAttachments: {
      ...s.sessionAttachments,
      [sessionId]: [...(s.sessionAttachments[sessionId] || []), file],
    },
  })),
  removeSessionAttachment: (sessionId, index) => set((s) => ({
    sessionAttachments: {
      ...s.sessionAttachments,
      [sessionId]: (s.sessionAttachments[sessionId] || []).filter((_, i) => i !== index),
    },
  })),
  clearSessionAttachments: (sessionId) => set((s) => ({
    sessionAttachments: { ...s.sessionAttachments, [sessionId]: [] },
  })),
  truncateMessages: (sessionId, toIndex) => set((s) => ({
    sessionMessages: {
      ...s.sessionMessages,
      [sessionId]: (s.sessionMessages[sessionId] || []).slice(0, toIndex + 1),
    },
  })),
  dismissQuestion: (sessionId) => set((s) => {
    const { [sessionId]: _, ...rest } = s.pendingQuestions;
    return { pendingQuestions: rest };
  }),
  updatePendingQuestionRequestId: (sessionId, questionText, requestId) => set((s) => {
    const current = s.pendingQuestions[sessionId] || [];
    return {
      pendingQuestions: {
        ...s.pendingQuestions,
        [sessionId]: current.map((q) =>
          q.question === questionText ? { ...q, request_id: requestId } : q
        ),
      },
    };
  }),
}));
