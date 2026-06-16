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
  role: 'user' | 'assistant';
  content: string;
}

interface SessionState {
  sessions: Session[];
  messages: Message[];
  activeSessionId: string | null;
  loading: boolean;
  setSessions: (sessions: Session[]) => void;
  setMessages: (messages: Message[]) => void;
  appendMessage: (message: Message) => void;
  setActiveSession: (id: string | null) => void;
  setLoading: (loading: boolean) => void;
  addSession: (session: Session) => void;
  removeSession: (id: string) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  messages: [],
  activeSessionId: null,
  loading: false,
  setSessions: (sessions) => set({ sessions }),
  setMessages: (messages) => set({ messages }),
  appendMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),
  setActiveSession: (id) => set({ activeSessionId: id }),
  setLoading: (loading) => set({ loading }),
  addSession: (session) => set((s) => ({ sessions: [...s.sessions, session] })),
  removeSession: (id) => set((s) => ({ sessions: s.sessions.filter((x) => x.id !== id) })),
}));
