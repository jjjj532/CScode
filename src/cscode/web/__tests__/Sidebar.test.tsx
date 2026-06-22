/**
 * Sidebar Component Tests
 * Tests session management: selection, deletion, race conditions
 */
import React from 'react';
import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Sidebar } from '../src/components/layout/Sidebar';
import { useSessionStore } from '../src/stores/useSessionStore';
import { useUIStore } from '../src/stores/useUIStore';

jest.mock('../src/lib/api', () => ({
  api: {
    sessions: {
      list: jest.fn(),
      create: jest.fn(),
      delete: jest.fn(),
      update: jest.fn(),
      export: jest.fn(),
      import: jest.fn(),
      messages: jest.fn(),
    },
  },
}));

import { api } from '../src/lib/api';

const mockSession1 = {
  id: 'session_1',
  title: 'Session 1',
  provider: 'openai',
  model: 'gpt-4',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

const mockSession2 = {
  id: 'session_2',
  title: 'Session 2',
  provider: 'anthropic',
  model: 'claude-3',
  created_at: '2024-01-02T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
};

const mockMessages1 = [
  { role: 'user' as const, content: 'Hello from Session 1' },
  { role: 'assistant' as const, content: 'Hi from Session 1' },
];

const mockMessages2 = [
  { role: 'user' as const, content: 'Hello from Session 2' },
];

async function renderSidebar() {
  const result = render(<Sidebar />);
  await waitFor(() => {
    expect(api.sessions.list).toHaveBeenCalled();
  });
  return result;
}

describe('Sidebar Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.sessions.list as jest.Mock).mockResolvedValue([]);
    (api.sessions.delete as jest.Mock).mockResolvedValue(undefined);
    (api.sessions.create as jest.Mock).mockResolvedValue(mockSession1);
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    useSessionStore.setState({
      sessions: [],
      sessionMessages: {},
      activeSessionId: null,
      loading: false,
      loadingSessionId: null,
    });
    useUIStore.setState({ sidebarOpen: true });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  // ─── RENDERING ──────────────────────────────────

  test('renders empty state when no sessions exist', async () => {
    await renderSidebar();
    expect(screen.getByText(/No sessions yet/)).toBeInTheDocument();
  });

  test('renders sessions list', async () => {
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1, mockSession2]);
    await renderSidebar();
    expect(screen.getByText('Session 1')).toBeInTheDocument();
    expect(screen.getByText('Session 2')).toBeInTheDocument();
  });

  // ─── SESSION SELECTION ──────────────────────────

  test('selecting a session loads its messages', async () => {
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1]);
    (api.sessions.messages as jest.Mock).mockResolvedValue(mockMessages1);
    await renderSidebar();
    await userEvent.click(screen.getByText('Session 1'));
    await waitFor(() => {
      expect(api.sessions.messages).toHaveBeenCalledWith('session_1');
    });
    await waitFor(() => {
      const state = useSessionStore.getState();
      expect(state.activeSessionId).toBe('session_1');
      expect(state.sessionMessages['session_1']).toEqual(mockMessages1);
    });
  });

  test('selecting a different session switches active session and messages', async () => {
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1, mockSession2]);
    (api.sessions.messages as jest.Mock)
      .mockResolvedValueOnce(mockMessages1)
      .mockResolvedValue(mockMessages2);
    await renderSidebar();
    await userEvent.click(screen.getByText('Session 1'));
    await waitFor(() => {
      expect(useSessionStore.getState().activeSessionId).toBe('session_1');
    });
    await userEvent.click(screen.getByText('Session 2'));
    await waitFor(() => {
      const state = useSessionStore.getState();
      expect(state.activeSessionId).toBe('session_2');
      expect(state.sessionMessages['session_2']).toEqual(mockMessages2);
    });
  });

  // ─── SESSION DELETION ───────────────────────────

  test('deleting a non-active session removes it from sidebar without affecting current view', async () => {
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1, mockSession2]);
    useSessionStore.setState({
      sessions: [mockSession1, mockSession2],
      activeSessionId: 'session_1',
      sessionMessages: { session_1: mockMessages1 },
    });
    await renderSidebar();
    const deleteButtons = screen.getAllByTitle('Delete session');
    await userEvent.click(deleteButtons[1]);
    await waitFor(() => {
      expect(useSessionStore.getState().sessions).toHaveLength(1);
      expect(useSessionStore.getState().sessions[0].id).toBe('session_1');
    });
    expect(useSessionStore.getState().activeSessionId).toBe('session_1');
    expect(useSessionStore.getState().sessionMessages['session_1']).toEqual(mockMessages1);
  });

  test('deleting the active session clears messages and deselects', async () => {
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1, mockSession2]);
    useSessionStore.setState({
      sessions: [mockSession1, mockSession2],
      activeSessionId: 'session_1',
      sessionMessages: { session_1: mockMessages1 },
    });
    await renderSidebar();
    const deleteButtons = screen.getAllByTitle('Delete session');
    await userEvent.click(deleteButtons[0]);
    await waitFor(() => {
      const state = useSessionStore.getState();
      expect(state.activeSessionId).toBeNull();
      expect(state.sessionMessages['session_1']).toEqual([]);
      expect(state.sessions).toHaveLength(1);
    });
  });

  test('cancelling delete confirmation does not delete session', async () => {
    (window.confirm as jest.Mock).mockReturnValue(false);
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1]);
    useSessionStore.setState({ sessions: [mockSession1] });
    await renderSidebar();
    const deleteButtons = screen.getAllByTitle('Delete session');
    await userEvent.click(deleteButtons[0]);
    expect(api.sessions.delete).not.toHaveBeenCalled();
    expect(useSessionStore.getState().sessions).toHaveLength(1);
  });

  // ─── NEW SESSION ─────────────────────────────────────

  test('creating a new session adds it to the list and activates it', async () => {
    const newSession = { ...mockSession1, id: 'session_new', title: 'New Session' };
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1]);
    (api.sessions.create as jest.Mock).mockResolvedValue(newSession);
    await renderSidebar();
    await userEvent.click(screen.getByTitle('New session'));
    await waitFor(() => {
      expect(api.sessions.create).toHaveBeenCalled();
    });
    await waitFor(() => {
      const state = useSessionStore.getState();
      expect(state.sessions).toHaveLength(2);
      expect(state.sessions.find((s) => s.id === 'session_new')).toBeTruthy();
      expect(state.activeSessionId).toBe('session_new');
    });
  });

  test('creating a new session switches to it even if viewing another', async () => {
    let resolveCreate!: (value: unknown) => void;
    const createDeferred = new Promise((resolve) => {
      resolveCreate = resolve;
    });
    const newSession = { ...mockSession1, id: 'session_new', title: 'New Session' };
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1, mockSession2]);
    (api.sessions.create as jest.Mock).mockReturnValue(createDeferred);
    (api.sessions.messages as jest.Mock).mockResolvedValue(mockMessages2);
    useSessionStore.setState({
      sessions: [mockSession1, mockSession2],
      activeSessionId: 'session_1',
      sessionMessages: { session_1: mockMessages1 },
    });
    await renderSidebar();
    await userEvent.click(screen.getByTitle('New session'));
    expect(api.sessions.create).toHaveBeenCalled();
    await userEvent.click(screen.getByText('Session 2'));
    await waitFor(() => {
      expect(useSessionStore.getState().activeSessionId).toBe('session_2');
    });
    (api.sessions.create as jest.Mock).mockResolvedValue(newSession);
    await act(async () => {
      resolveCreate(newSession);
    });
    await waitFor(() => {
      const state = useSessionStore.getState();
      // handleNewSession's setActiveSession(newSession.id) runs AFTER the resolved deferred,
      // so the active session switches to the new session
      expect(state.activeSessionId).toBe('session_new');
      expect(state.sessions).toHaveLength(3);
    });
  });

  // ─── RACE CONDITION: DELETE ──────────────────────────

  test('race condition: selecting then immediately deleting a session does not show stale messages', async () => {
    let resolveMessages!: (value: unknown) => void;
    const messagesDeferred = new Promise((resolve) => {
      resolveMessages = resolve;
    });
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1, mockSession2]);
    (api.sessions.messages as jest.Mock).mockReturnValue(messagesDeferred);
    await renderSidebar();
    await userEvent.click(screen.getByText('Session 1'));
    expect(useSessionStore.getState().activeSessionId).toBe('session_1');
    const deleteButtons = screen.getAllByTitle('Delete session');
    await userEvent.click(deleteButtons[0]);
    await act(async () => {
      resolveMessages(mockMessages1);
    });
    await waitFor(() => {
      const state = useSessionStore.getState();
      expect(state.activeSessionId).toBeNull();
      expect(state.sessionMessages['session_1']).toEqual([]);
    });
    expect(api.sessions.messages).toHaveBeenCalledWith('session_1');
  });

  test('race condition: rapid session switching discards stale messages', async () => {
    let resolveMessages1!: (value: unknown) => void;
    const messages1Deferred = new Promise((resolve) => {
      resolveMessages1 = resolve;
    });
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1, mockSession2]);
    (api.sessions.messages as jest.Mock)
      .mockReturnValueOnce(messages1Deferred)
      .mockResolvedValue(mockMessages2);
    await renderSidebar();
    await userEvent.click(screen.getByText('Session 1'));
    expect(useSessionStore.getState().activeSessionId).toBe('session_1');
    await userEvent.click(screen.getByText('Session 2'));
    expect(useSessionStore.getState().activeSessionId).toBe('session_2');
    await act(async () => {
      resolveMessages1(mockMessages1);
    });
    await waitFor(() => {
      const state = useSessionStore.getState();
      expect(state.activeSessionId).toBe('session_2');
      expect(state.sessionMessages['session_2']).toEqual(mockMessages2);
      // Stale messages for session 1 are correctly discarded by the guard
      expect(state.sessionMessages['session_1']).toBeUndefined();
    });
  });

  test('race condition: deleting a session while user switches to another does not clear the other sessions messages', async () => {
    let resolveDelete!: (value: unknown) => void;
    const deleteDeferred = new Promise((resolve) => {
      resolveDelete = resolve;
    });
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1, mockSession2]);
    (api.sessions.delete as jest.Mock).mockReturnValue(deleteDeferred);
    (api.sessions.messages as jest.Mock).mockResolvedValue(mockMessages2);
    useSessionStore.setState({
      sessions: [mockSession1, mockSession2],
      activeSessionId: 'session_1',
      sessionMessages: { session_1: mockMessages1 },
    });
    await renderSidebar();
    const deleteButtons = screen.getAllByTitle('Delete session');
    await userEvent.click(deleteButtons[0]);
    expect(api.sessions.delete).toHaveBeenCalledWith('session_1');
    await userEvent.click(screen.getByText('Session 2'));
    await waitFor(() => {
      expect(useSessionStore.getState().activeSessionId).toBe('session_2');
      expect(useSessionStore.getState().sessionMessages['session_2']).toEqual(mockMessages2);
    });
    await act(async () => {
      resolveDelete(undefined);
    });
    await waitFor(() => {
      const state = useSessionStore.getState();
      expect(state.activeSessionId).toBe('session_2');
      expect(state.sessionMessages['session_2']).toEqual(mockMessages2);
    });
  });

  test('race condition: messages fetched for a deleted session are discarded even if delete API is slow', async () => {
    let resolveDelete!: (value: unknown) => void;
    let resolveMessages!: (value: unknown) => void;
    const deleteDeferred = new Promise((resolve) => {
      resolveDelete = resolve;
    });
    const messagesDeferred = new Promise((resolve) => {
      resolveMessages = resolve;
    });
    (api.sessions.list as jest.Mock).mockResolvedValue([mockSession1, mockSession2]);
    (api.sessions.messages as jest.Mock).mockReturnValue(messagesDeferred);
    (api.sessions.delete as jest.Mock).mockReturnValue(deleteDeferred);
    useSessionStore.setState({
      sessions: [mockSession1, mockSession2],
      activeSessionId: 'session_1',
      sessionMessages: { session_1: mockMessages1 },
    });
    await renderSidebar();
    const deleteButtons = screen.getAllByTitle('Delete session');
    await userEvent.click(deleteButtons[0]);
    expect(useSessionStore.getState().activeSessionId).toBe('session_1');
    expect(useSessionStore.getState().sessionMessages['session_1']).toEqual(mockMessages1);
    await act(async () => {
      resolveMessages(mockMessages1);
    });
    expect(useSessionStore.getState().activeSessionId).toBe('session_1');
    await act(async () => {
      resolveDelete(undefined);
    });
    await waitFor(() => {
      const state = useSessionStore.getState();
      expect(state.activeSessionId).toBeNull();
      expect(state.sessionMessages['session_1']).toEqual([]);
    });
  });
});
