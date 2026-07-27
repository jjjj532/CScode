import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { useConfigStore } from '../src/stores/useConfigStore';
import { useSessionStore } from '../src/stores/useSessionStore';

// Mock ESM deps that Jest can't parse
jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }: any) => <div>{children}</div>,
}));
jest.mock('remark-gfm', () => () => {});
jest.mock('rehype-highlight', () => () => {});

// Mock PtyTerminal to avoid Canvas/WebGL errors in jsdom
jest.mock('../src/components/PtyTerminal', () => ({
  PtyTerminal: () => null,
}));

const mockAddToast = jest.fn();
jest.mock('../src/stores/useToastStore', () => ({
  useToastStore: (selector: any) => selector({
    toasts: [],
    addToast: mockAddToast,
    removeToast: jest.fn(),
  }),
}));

jest.mock('../src/stores/useUIStore', () => ({
  useUIStore: (selector: any) => selector({
    settingsOpen: false,
    sidebarOpen: true,
    setSettingsOpen: jest.fn(),
    setSidebarOpen: jest.fn(),
  }),
}));

import App from '../src/App';

const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  jest.clearAllMocks();
  useConfigStore.setState({ config: null, loading: false });
  useSessionStore.setState({
    sessions: [],
    sessionMessages: {},
    sessionMessageVersion: {},
    activeSessionId: null,
    sessionLoading: {},
    sessionToolCalls: {},
    sessionThinking: {},
    sessionLastSeq: {},
    sessionAttachments: {},
    pendingQuestions: {},
  });
});

describe('App Component', () => {
  test('renders without crashing', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole('main')).toBeInTheDocument();
    });
  });

  test('sets loading true before config fetch and false after', async () => {
    let resolveConfig!: (value: unknown) => void;
    const configPromise = new Promise((resolve) => { resolveConfig = resolve; });
    mockFetch.mockReturnValue(configPromise);

    render(<App />);
    expect(useConfigStore.getState().loading).toBe(true);

    await act(async () => {
      resolveConfig({
        ok: true,
        json: () => Promise.resolve({ provider: 'openai', model: 'gpt-4' }),
      });
    });

    await waitFor(() => {
      expect(useConfigStore.getState().loading).toBe(false);
    });
  });

  test('shows error toast when config fetch fails', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    render(<App />);

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        expect.stringContaining('Failed to load'),
        'error',
      );
    });
  });

  test('sets loading to false after fetch error (no stuck loading)', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    render(<App />);

    await waitFor(() => {
      expect(useConfigStore.getState().loading).toBe(false);
    });
  });
});
