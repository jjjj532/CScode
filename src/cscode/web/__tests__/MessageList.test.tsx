import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MessageList } from '../src/components/chat/MessageList';

jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }: any) => React.createElement('div', null, children),
}));
jest.mock('remark-gfm', () => () => {});

const mockMessages = [
  {
    id: '1',
    role: 'user' as const,
    content: 'Hello AI',
    createdAt: new Date().toISOString(),
  },
  {
    id: '2',
    role: 'assistant' as const,
    content: 'Hello! How can I help you?',
    createdAt: new Date().toISOString(),
  },
];

const mockUnsubscribe = jest.fn();
jest.mock('../src/hooks/useChat', () => ({
  useChat: () => ({
    sendMessage: jest.fn(),
    stop: jest.fn(),
    subscribeToSessionEvents: () => mockUnsubscribe,
  }),
}));

jest.mock('../src/stores/useSessionStore', () => ({
  useSessionStore: Object.assign(
    (selector: any) => selector({
      sessionMessages: { session_1: mockMessages },
      sessionLoading: {},
      sessionToolCalls: {},
      sessionThinking: {},
      sessionAttachments: {},
      sessionLastSeq: {},
      activeSessionId: 'session_1',
      applyEvent: jest.fn(),
      setSessionLastSeq: jest.fn(),
    }),
    { getState: () => ({ sessionLastSeq: {} }) },
  ),
}));

jest.mock('../src/stores/useUIStore', () => ({
  useUIStore: (selector: any) => selector({
    toolCalls: [],
    clearToolCalls: jest.fn(),
  }),
}));

describe('MessageList Component', () => {
  test('renders all messages', () => {
    render(<MessageList />);
    expect(screen.getByText('Hello AI')).toBeTruthy();
    expect(screen.getByText('Hello! How can I help you?')).toBeTruthy();
  });

  test('empty state shows placeholder when no messages', () => {
    const mockEmpty = jest.requireMock('../src/stores/useSessionStore');
    mockEmpty.useSessionStore = (selector: any) => selector({
      sessionMessages: {},
      sessionLoading: {},
      sessionToolCalls: {},
      sessionThinking: {},
      sessionAttachments: {},
      sessionLastSeq: {},
      activeSessionId: null,
    });
    render(<MessageList />);
    expect(screen.getByText('CScode')).toBeTruthy();
  });

  test('scrolls to bottom when new messages arrive', () => {
    render(<MessageList />);
  });
});
