import { create } from 'zustand';

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
  setSessions: (sessions) => set({ sessions }),
  setSessionLastSeq: (sessionId, seq) => set((s) => ({
    sessionLastSeq: { ...s.sessionLastSeq, [sessionId]: seq },
  })),
  applyEvent: (sessionId, event) => set((s) => {
    const d = event.data;
    switch (event.type) {
      case 'step.started':
        return {
          sessionThinking: { ...s.sessionThinking, [sessionId]: true },
          sessionToolCalls: { ...s.sessionToolCalls, [sessionId]: [] },
        };
      case 'text.ended': {
        const content = d?.content;
        if (!content?.trim()) return s;
        return {
          sessionThinking: { ...s.sessionThinking, [sessionId]: false },
          sessionMessages: {
            ...s.sessionMessages,
            [sessionId]: [
              ...(s.sessionMessages[sessionId] || []),
              { role: 'assistant' as const, content, created_at: new Date().toISOString() },
            ],
          },
        };
      }
      case 'tool.called': {
        const argsStr = d?.args ? (typeof d.args === 'object' ? JSON.stringify(d.args) : String(d.args)) : '';
        return {
          sessionThinking: { ...s.sessionThinking, [sessionId]: false },
          sessionToolCalls: {
            ...s.sessionToolCalls,
            [sessionId]: [
              ...(s.sessionToolCalls[sessionId] || []),
              { name: d?.name || '', args: argsStr, status: 'running' as const, round: d?.round || 0, max: d?.max || 0, stepLog: [] },
            ],
          },
        };
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
        return { sessionThinking: { ...s.sessionThinking, [sessionId]: false } };
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
}));
