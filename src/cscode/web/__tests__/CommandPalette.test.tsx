import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { CommandPalette } from '../src/components/ui/CommandPalette';

// Mock stores
jest.mock('../src/stores/useUIStore', () => ({
  useUIStore: (selector: any) => selector({
    theme: 'opencode-dark',
    sidebarOpen: true,
    mode: 'build',
    setTheme: jest.fn(),
    setSidebarOpen: jest.fn(),
    toggleMode: jest.fn(),
    setSettingsOpen: jest.fn(),
  }),
}));

jest.mock('../src/stores/useSessionStore', () => ({
  useSessionStore: (selector: any) => selector({
    sessions: [],
    addSession: jest.fn(),
    setActiveSession: jest.fn(),
    setMessages: jest.fn(),
  }),
}));

jest.mock('../src/stores/useConfigStore', () => ({
  useConfigStore: (selector: any) => selector({ config: null }),
}));

jest.mock('../src/stores/useToastStore', () => ({
  useToastStore: (selector: any) => selector({
    addToast: jest.fn(),
  }),
}));

jest.mock('../src/lib/api', () => ({
  api: {
    session: {
      create: jest.fn(),
    },
  },
}));

describe('CommandPalette Component', () => {
  test('close button has aria-label', () => {
    render(<CommandPalette />);

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { metaKey: true, key: 'k' }));
    });

    const allButtons = screen.getAllByRole('button');
    const closeBtn = allButtons.find(
      (btn) => btn.querySelector('svg') && !btn.textContent?.trim()
    );
    expect(closeBtn).toBeTruthy();
    expect(closeBtn).toHaveAttribute('aria-label');
  });
});
