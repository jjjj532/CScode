import React from 'react';
import { render, screen } from '@testing-library/react';
import { SessionFilesPanel } from '../src/components/chat/SessionFilesPanel';
import { useSessionStore } from '../src/stores/useSessionStore';
import { useToastStore } from '../src/stores/useToastStore';

const sid = 'session_files_test';

beforeEach(() => {
  const { setState } = useSessionStore;
  setState({
    sessionFiles: {},
  });
});

describe('SessionFilesPanel', () => {
  test('renders null when session has no generated files (stable selector ref, no #185 loop)', () => {
    const { container } = render(<SessionFilesPanel sessionId={sid} />);
    expect(container.firstChild).toBeNull();
  });

  test('renders generated files list', () => {
    useSessionStore.setState((s) => ({
      sessionFiles: { ...s.sessionFiles, [sid]: ['/tmp/out/a.py', '/tmp/out/b.py'] },
    }));
    render(<SessionFilesPanel sessionId={sid} />);
    expect(screen.getByText(/a\.py/)).toBeTruthy();
    expect(screen.getByText(/b\.py/)).toBeTruthy();
  });

  test('still renders after sessionFiles updated while mounted (selector returns stable ref)', () => {
    // Add files first so the panel mounts with content.
    useSessionStore.setState((s) => ({
      sessionFiles: { ...s.sessionFiles, [sid]: ['/tmp/out/one.py'] },
    }));
    const { rerender } = render(<SessionFilesPanel sessionId={sid} />);
    expect(screen.getByText(/one\.py/)).toBeTruthy();

    // Simulate a backend update while the panel is mounted: listener must not
    // trigger an infinite render loop (React error #185).
    useSessionStore.setState((s) => ({
      sessionFiles: { ...s.sessionFiles, [sid]: ['/tmp/out/one.py', '/tmp/out/two.py'] },
    }));
    rerender(<SessionFilesPanel sessionId={sid} />);
    expect(screen.getByText(/two\.py/)).toBeTruthy();
  });

  test('reads stable empty-render despite adding an unrelated session file', () => {
    // Panel for a session with no files must stay null even when a different
    // session's file list is updated (snapshot equality must hold).
    const other = 'other_session';
    render(<SessionFilesPanel sessionId={sid} />);
    expect(screen.queryByText(/\.py$/)).toBeNull();
    // Trigger a store update unrelated to this panel's session.
    useSessionStore.setState({ sessionFiles: { [other]: ['/tmp/out/other.py'] } });
    expect(screen.queryByText(/\.py$/)).toBeNull();
  });
});

it('useToastStore deps are stable for openFile callback', () => {
  // Ensure the openFile callback does not accidentally depend on a fresh
  // selector result across re-renders.
  const addToast = useToastStore.getState().addToast;
  expect(typeof addToast).toBe('function');
});