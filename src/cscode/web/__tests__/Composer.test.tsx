import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Composer } from '../src/components/chat/Composer';

const mockSendMessage = jest.fn();
const mockStop = jest.fn();
let streamSessionOverride: string | null = null;
let loadingSessionOverride: Record<string, boolean> = {};

jest.mock('../src/hooks/useChat', () => ({
  useChat: () => ({
    sendMessage: mockSendMessage,
    stop: mockStop,
    subscribeToSessionEvents: () => jest.fn(),
  }),
  isSessionStreaming: (sid: string) => sid === streamSessionOverride,
}));

jest.mock('../src/stores/useSessionStore', () => ({
  useSessionStore: (selector: any) => selector({
    sessionLoading: loadingSessionOverride,
    sessionToolCalls: {},
    sessionThinking: {},
    sessionAttachments: {},
    activeSessionId: 'session_1',
  }),
}));

jest.mock('../src/stores/useUIStore', () => ({
  useUIStore: (selector: any) => selector({
    attachedFiles: [],
    removeAttachedFile: jest.fn(),
    clearAttachedFiles: jest.fn(),
    addAttachedFile: jest.fn(),
  }),
}));

jest.mock('../src/stores/useConfigStore', () => ({
  useConfigStore: (selector: any) => selector({
    config: { model: 'gpt-4o', provider: 'openai' },
  }),
}));

describe('Composer Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    streamSessionOverride = null;
    loadingSessionOverride = {};
  });

  test('renders input field', () => {
    render(<Composer />);
    const input = screen.getByPlaceholderText(/Ask anything/i);
    expect(input).toBeTruthy();
  });

  test('renders send button', () => {
    render(<Composer />);
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(2);
  });

  test('send button is disabled when input is empty', () => {
    render(<Composer />);
    const sendButton = screen.getAllByRole('button')[1];
    expect(sendButton).toBeDisabled();
  });

  test('send button is enabled when input has text', async () => {
    const user = userEvent.setup();
    render(<Composer />);
    const input = screen.getByPlaceholderText(/Ask anything/i);
    await user.type(input, 'Hello');
    const sendButton = screen.getAllByRole('button')[1];
    expect(sendButton).not.toBeDisabled();
  });

  test('calls sendMessage when send button is clicked', async () => {
    const user = userEvent.setup();
    render(<Composer />);
    const input = screen.getByPlaceholderText(/Ask anything/i);
    await user.type(input, 'Test message');
    const sendButton = screen.getAllByRole('button')[1];
    await user.click(sendButton);
    expect(mockSendMessage).toHaveBeenCalled();
  });

  test('clears input after sending message', async () => {
    const user = userEvent.setup();
    render(<Composer />);
    const input = screen.getByPlaceholderText(/Ask anything/i) as HTMLTextAreaElement;
    await user.type(input, 'Test message');
    const sendButton = screen.getAllByRole('button')[1];
    await user.click(sendButton);
    expect(input.value).toBe('');
  });

  test('shows file attachment button', () => {
    const { container } = render(<Composer />);
    const attachButton = container.querySelector('button');
    expect(attachButton).toBeTruthy();
  });

  test('shows stop button while session is loading', () => {
    loadingSessionOverride = { session_1: true };
    render(<Composer />);
    const stopButton = screen.queryByRole('button', { name: /Stop generation/i });
    expect(stopButton).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Send message/i })).toBeNull();
  });

  test('shows stop button while session is streaming even when sessionLoading is false', () => {
    // The bug: stop button only checked sessionLoading, so a session whose stream
    // is running (activeStreams has the id) but whose loading flag was not set
    // showed a blue send button instead of a red stop button.
    streamSessionOverride = 'session_1';
    loadingSessionOverride = { session_1: false };
    render(<Composer />);
    const stopButton = screen.queryByRole('button', { name: /Stop generation/i });
    expect(stopButton).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Send message/i })).toBeNull();
  });

  test('renders with placeholder text', () => {
    render(<Composer />);
    const input = screen.getByPlaceholderText(/Ask anything/i);
    expect(input).toHaveAttribute('placeholder');
  });

  test('Enter key sends message', async () => {
    const user = userEvent.setup();
    render(<Composer />);
    const input = screen.getByPlaceholderText(/Ask anything/i);
    await user.type(input, 'Hello');
    await user.keyboard('{Enter}');
    expect(mockSendMessage).toHaveBeenCalled();
  });

  test('fireEvent.change properly syncs React state', () => {
    render(<Composer />);
    const input = screen.getByPlaceholderText(/Ask anything/i);
    const sendButton = screen.getAllByRole('button')[1] as HTMLButtonElement;
    fireEvent.change(input, { target: { value: 'Hello from fireEvent' } });
    expect((input as HTMLTextAreaElement).value).toBe('Hello from fireEvent');
    expect(sendButton).not.toBeDisabled();
  });

  test('direct DOM value assignment does NOT sync React state', () => {
    render(<Composer />);
    const input = screen.getByPlaceholderText(/Ask anything/i) as HTMLTextAreaElement;
    const sendButton = screen.getAllByRole('button')[1] as HTMLButtonElement;
    input.value = 'direct DOM set';
    fireEvent(input, new Event('input', { bubbles: true }));
    expect((input as HTMLTextAreaElement).value).toBe('direct DOM set');
    // React controlled component — only onChange (change event) syncs state,
    // not raw DOM mutation + input event. This is expected React behavior.
    expect(sendButton).toBeDisabled();
  });
});
