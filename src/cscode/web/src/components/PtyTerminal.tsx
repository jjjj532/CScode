import { useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';

interface PtySession {
  session_id: string;
  shell: string;
  cwd: string;
  created_at: number;
}

async function ptyRequest(body: Record<string, unknown>): Promise<Record<string, unknown>> {
  const res = await fetch('/api/pty', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`PTY error ${res.status}: ${text}`);
  }
  return res.json();
}

export function PtyTerminal() {
  const terminalRef = useRef<HTMLDivElement>(null);
  const termInstance = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [activeSessions, setActiveSessions] = useState<PtySession[]>([]);
  const [command, setCommand] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!terminalRef.current || termInstance.current) return;

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: 'bar',
      fontSize: 13,
      fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
      theme: {
        background: '#1a1b26',
        foreground: '#a9b1d6',
        cyan: '#7dcfff',
        green: '#9ece6a',
        red: '#f7768e',
        yellow: '#e0af68',
        blue: '#7aa2f7',
        magenta: '#bb9af7',
      },
      rows: 15,
      cols: 80,
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    fitAddonRef.current = fitAddon;

    term.open(terminalRef.current);

    term.onData((data) => {
      // For now, log typed data — future: send to PTY session
      console.log('[PTY] input:', data);
    });

    termInstance.current = term;

    // Fit after mount
    setTimeout(() => fitAddon.fit(), 50);

    term.writeln('\x1b[36mCScode PTY Terminal\x1b[0m');
    term.writeln('Type a command below and press Execute.');
    term.writeln('');

    return () => {
      term.dispose();
      termInstance.current = null;
    };
  }, []);

  useEffect(() => {
    const handleResize = () => fitAddonRef.current?.fit();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleCreate = async () => {
    setLoading(true);
    try {
      const data = await ptyRequest({ action: 'create', shell: '/bin/bash' });
      const sid = data.session_id as string;
      setSessionId(sid);
      const term = termInstance.current;
      if (term) term.writeln(`\x1b[32mSession created: ${sid}\x1b[0m`);
      await refreshSessions();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      termInstance.current?.writeln(`\x1b[31mError: ${msg}\x1b[0m`);
    } finally {
      setLoading(false);
    }
  };

  const handleExec = async () => {
    if (!sessionId || !command.trim()) return;
    setLoading(true);
    try {
      const data = await ptyRequest({
        action: 'exec',
        session_id: sessionId,
        command: command.trim(),
      });
      const output = (data.output as string) || '';
      const exitCode = data.exit_code as number;
      const term = termInstance.current;
      if (term) {
        term.writeln(output);
        term.writeln(`\x1b[90mExit code: ${exitCode}\x1b[0m`);
      }
      setCommand('');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      termInstance.current?.writeln(`\x1b[31mError: ${msg}\x1b[0m`);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      await ptyRequest({ action: 'close', session_id: sessionId });
      const term = termInstance.current;
      if (term) term.writeln(`\x1b[33mSession closed: ${sessionId}\x1b[0m`);
      setSessionId(null);
      await refreshSessions();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      termInstance.current?.writeln(`\x1b[31mError: ${msg}\x1b[0m`);
    } finally {
      setLoading(false);
    }
  };

  const refreshSessions = async () => {
    try {
      const data = await ptyRequest({ action: 'list' });
      setActiveSessions((data.sessions || []) as PtySession[]);
    } catch {
      // silently fail
    }
  };

  return (
    <div style={{
      borderTop: '1px solid #2c2c2c',
      background: '#1a1b26',
      color: '#a9b1d6',
      fontSize: 13,
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 12px',
        borderBottom: '1px solid #2c2c2c',
      }}>
        <span style={{ fontWeight: 600, fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
          Terminal
        </span>
        {sessionId && (
          <span style={{ fontSize: 11, color: '#565f89' }}>
            Session: {sessionId.slice(0, 8)}
          </span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <button onClick={handleCreate} disabled={loading}
            style={btnStyle(loading || !!sessionId)}>
            New
          </button>
          <button onClick={handleExec} disabled={loading || !sessionId || !command.trim()}
            style={btnStyle(loading || !sessionId || !command.trim())}>
            Run
          </button>
          <button onClick={handleClose} disabled={loading || !sessionId}
            style={btnStyle(loading || !sessionId)}>
            Close
          </button>
        </div>
      </div>
      <div ref={terminalRef} style={{ padding: '4px 8px' }} />
      <div style={{ display: 'flex', padding: '4px 8px', gap: 4 }}>
        <input
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleExec(); }}
          placeholder={sessionId ? 'Enter command...' : 'Create a session first'}
          disabled={!sessionId}
          style={{
            flex: 1,
            background: '#24283b',
            border: '1px solid #2c2c2c',
            color: '#a9b1d6',
            padding: '6px 10px',
            fontSize: 13,
            borderRadius: 4,
            outline: 'none',
          }}
        />
      </div>
    </div>
  );
}

function btnStyle(disabled: boolean): React.CSSProperties {
  return {
    background: disabled ? '#1f2335' : '#3b4261',
    border: '1px solid #2c2c2c',
    color: disabled ? '#565f89' : '#a9b1d6',
    padding: '4px 12px',
    fontSize: 12,
    borderRadius: 4,
    cursor: disabled ? 'not-allowed' : 'pointer',
  };
}
