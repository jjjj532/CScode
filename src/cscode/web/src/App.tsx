import { useState, useRef, useEffect, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { SettingsPanel } from './components/SettingsPanel';
import { useConfig } from './context/ConfigContext';
import { Message } from './types';

const sessionMessagesCache = new Map<string, Message[]>();

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const fallbackInputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const pendingSessionRef = useRef<string | null>(null);
  const pendingFilesRef = useRef<string[]>([]);
  const activeStreamSessionRef = useRef<string | null>(null);  // Track which session has active stream
  const [toolProgress, setToolProgress] = useState<{ type: string; name?: string; round?: number; max?: number; stepLog?: string[] } | null>(null);
  const [toast, setToast] = useState<{ msg: string; err?: boolean } | null>(null);
  const [progressLogs, setProgressLogs] = useState<string[]>([]);  // Track all progress steps

  const handleAttachFile = async () => {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const { readFile } = await import('@tauri-apps/plugin-fs');
      const selected = await open({ multiple: true, title: 'Select files to attach' });
      if (!selected) return;
      const paths = Array.isArray(selected) ? selected : [selected];
      const newFiles: File[] = [];
      for (const filePath of paths) {
        const name = filePath.split('/').pop() || filePath.split('\\').pop() || 'file';
        const content = await readFile(filePath);
        newFiles.push(new File([content], name));
      }
      setAttachedFiles(prev => [...prev, ...newFiles]);
    } catch {
      fallbackInputRef.current?.click();
    }
  };

  const handleStop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setLoading(false);
    setToolProgress(null);
    setMessages(prev => prev.filter(m => m.content !== 'Thinking...'));
  }, []);
  const { currentSession, setCurrentSession, config, loadSessionMessages, createSession, loadSessions } = useConfig();

  const handleFileLinkClick = async (e: React.MouseEvent, rawUrl: string) => {
    e.preventDefault();
    let fname = rawUrl;
    for (const prefix of ['/tmp/cscode-outputs/', 'file:///tmp/cscode-outputs/', '/outputs/']) {
      if (fname.startsWith(prefix)) { fname = fname.slice(prefix.length); break; }
    }
    fname = fname.replace(/[.,;:!?)\]}·`。，、：；？！》】」'"…]+$/, '');
    try { fname = decodeURIComponent(fname); } catch {}
    try {
      const { save } = await import('@tauri-apps/plugin-dialog');
      const { writeFile } = await import('@tauri-apps/plugin-fs');
      const res = await fetch('/api/download/' + encodeURIComponent(fname));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const buf = await res.arrayBuffer();
      const savePath = await save({ defaultPath: fname });
      if (savePath) {
        await writeFile(savePath, new Uint8Array(buf));
        setToast({ msg: '✅ Saved: ' + fname });
      }
    } catch (e: any) {
      const msg = e.message || String(e);
      if (!msg.includes('ACL')) {
        setToast({ msg: '❌ ' + msg, err: true });
      }
    }
    setTimeout(() => setToast(null), 4000);
  };

  const renderContent = useCallback((text: string) => {
    const urlRegex = /(\/outputs\/[^\s<>"'\])}]+|\/tmp\/cscode-outputs\/[^\s<>"'\])}]+|file:\/\/\/tmp\/cscode-outputs\/[^\s<>"'\])}]+|https?:\/\/[^\s<>"'\])}]+)/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = urlRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index));
      }
      let url = match[0];
      url = url.replace(/[.,;:!?)\]}·`。，、：；？！》】」'"…]+$/, '');
      let displayUrl = url;
      for (const prefix of ['/tmp/cscode-outputs/', 'file:///tmp/cscode-outputs/']) {
        if (displayUrl.startsWith(prefix)) { displayUrl = '/outputs/' + displayUrl.slice(prefix.length); break; }
      }
      try { displayUrl = decodeURIComponent(displayUrl); } catch {}
      parts.push(
        <a key={match.index} href="#"
           onClick={(e) => handleFileLinkClick(e, url)}
           style={{ color: '#646cff', textDecoration: 'underline', cursor: 'pointer' }}>
          {displayUrl}
        </a>
      );
      lastIndex = match.index + url.length;
    }
    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex));
    }
    return parts.length > 0 ? parts : text;
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleNewChat = async () => {
    // Clear messages first
    setMessages([]);
    setToolProgress(null);
    // Create new session
    const id = await createSession('New Chat');
    // Set as current and don't load old messages (empty session)
    setCurrentSession(id);
  };

  const handleSessionClick = (sessionId: string) => {
    // Cache current session's messages before switching
    if (currentSession && messages.length > 0) {
      sessionMessagesCache.set(currentSession, [...messages]);
    }
    // Switch session WITHOUT aborting - let current task continue in background
    setLoading(false);
    setAttachedFiles([]);
    setProgressLogs([]);  // Clear progress logs when switching
    setCurrentSession(sessionId);
  };

  // Load messages when session changes
  useEffect(() => {
    console.log("Session changed to:", currentSession, "active stream:", activeStreamSessionRef.current);

    // If we have cached messages for this session, use them first
    if (currentSession && sessionMessagesCache.has(currentSession)) {
      const cached = sessionMessagesCache.get(currentSession)!;
      console.log("Using cached messages:", cached.length);
      setMessages(cached);
      sessionMessagesCache.delete(currentSession);  // Clean up after using
      return;
    }

    // Skip loading from DB if this session has an active stream (task still running)
    if (currentSession && currentSession !== activeStreamSessionRef.current) {
      loadSessionMessages(currentSession).then(msgs => {
        console.log("Loaded messages from DB:", msgs.length);
        setMessages(msgs.filter(m => m.role === 'user' || m.role === 'assistant').map(m => ({ role: m.role as 'user' | 'assistant', content: m.content })));
      });
    } else if (!currentSession) {
      setMessages([]);
    }
    // Keep toolProgress when switching back to active session - don't clear it here
  }, [currentSession]);

  const sendMessage = async () => {
    if ((!input.trim() && attachedFiles.length === 0) || loading) return;

    const textContent = input.trim();
    const userMsg: Message = { role: 'user', content: textContent || '(attached files)' };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    setToolProgress({ type: 'thinking' });
    setProgressLogs([]);  // Clear previous logs
    // Add initial thinking message
    setMessages(prev => [...prev, { role: 'assistant', content: 'Thinking...' }]);
    activeStreamSessionRef.current = currentSession || pendingSessionRef.current || 'new';

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      let body: BodyInit;
      let headers: Record<string, string> = {};

      if (attachedFiles.length > 0) {
        const formData = new FormData();
        formData.append('message', textContent || '');
        if (currentSession) formData.append('session_id', currentSession);
        for (const file of attachedFiles) {
          formData.append('files', file);
        }
        body = formData;
      } else {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify({
          message: textContent,
          session_id: currentSession,
        });
      }

      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers,
        body,
        signal: controller.signal,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';
      let fullResponse = '';
      let responseReady = false;
      const wasNewSession = !currentSession;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let data: any;
          try {
            data = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          switch (data.type) {
            case 'session':
              console.log('DEBUG SSE: session', data.session_id);
              pendingSessionRef.current = data.session_id;
              activeStreamSessionRef.current = data.session_id;
              if (wasNewSession) loadSessions();
              break;
            case 'thinking':
              console.log('DEBUG SSE: thinking event');
              setToolProgress({ type: 'thinking' });
              setProgressLogs(prev => [...prev, '🤔 分析任务...']);
              // Append thinking step as separate message
              setMessages(prev => [...prev, { role: 'assistant', content: '🤔 分析任务...' }]);
              break;
            case 'tool:start':
              console.log('DEBUG SSE: tool:start', data.name, 'round:', data.round, '/', data.max);
              const toolStartMsg = `🔧 执行工具: ${data.name} (${data.round}/${data.max})`;
              setToolProgress({ type: 'tool', name: data.name, round: data.round, max: data.max });
              setProgressLogs(prev => [...prev, toolStartMsg]);
              // Append tool start as separate message
              setMessages(prev => [...prev, { role: 'assistant', content: toolStartMsg }]);
              break;
            case 'tool:complete':
              console.log('DEBUG SSE: tool:complete', data.name, 'success:', data.success, 'intercepted:', data.intercepted);
              const toolCompleteMsg = data.intercepted
                ? `⏭️ 工具 ${data.name} 被拦截 (跳过)`
                : data.success
                  ? `✅ 工具 ${data.name} 完成`
                  : `❌ 工具 ${data.name} 失败`;
              setToolProgress({ type: 'thinking' });
              setProgressLogs(prev => [...prev, toolCompleteMsg]);
              // Append tool complete as separate message
              setMessages(prev => [...prev, { role: 'assistant', content: toolCompleteMsg }]);
              break;
            case 'file_created':
              console.log('DEBUG SSE: file_created', data.filename);
              const fileMsg = `📄 创建文件: ${data.filename}`;
              setProgressLogs(prev => [...prev, fileMsg]);
              setMessages(prev => [...prev, { role: 'assistant', content: fileMsg }]);
              pendingFilesRef.current.push(data.filename);
              break;
            case 'complete':
              console.log('DEBUG SSE: complete, response length:', data.content?.length);
              fullResponse = data.content;
              responseReady = true;
              break;
            case 'error':
              console.log('DEBUG SSE: error', data.content);
              fullResponse = 'Error: ' + (data.content || 'Unknown error');
              responseReady = true;
              break;
          }
        }
      }

      setToolProgress(null);
      activeStreamSessionRef.current = null;
      // Download files detected via SSE (quiet, no Finder popup)
      const filenames = pendingFilesRef.current;
      pendingFilesRef.current = [];
      for (const fname of filenames) {
        fetch('/api/download/' + encodeURIComponent(fname) + '?quiet=1')
          .then(r => r.json())
          .then(d => setToast({ msg: '✅ Saved to ~/Downloads/' + d.filename }))
          .catch(e => setToast({ msg: '❌ ' + e.message, err: true }));
        setTimeout(() => setToast(null), 4000);
      }

      if (responseReady) {
        // Update session after stream completes so messages aren't cleared
        if (pendingSessionRef.current && pendingSessionRef.current !== currentSession) {
          setCurrentSession(pendingSessionRef.current);
        }
        setMessages(prev => {
          const next = [...prev];
          if (next[next.length - 1]?.content === 'Thinking...') {
            next[next.length - 1] = { role: 'assistant', content: fullResponse };
          } else {
            next.push({ role: 'assistant', content: fullResponse });
          }
          return next;
        });
      }
    } catch (err) {
      setToolProgress(null);
      if (err instanceof DOMException && err.name === 'AbortError') {
        console.log('Request cancelled by user');
      } else {
        console.error('Chat error:', err);
        const errorMsg: Message = { role: 'assistant', content: 'Error: ' + String(err) };
        setMessages(prev => [...prev, errorMsg]);
      }
    } finally {
      setAttachedFiles([]);
      if (fallbackInputRef.current) fallbackInputRef.current.value = '';
      setLoading(false);
      abortRef.current = null;
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar 
        onSettingsClick={() => setSettingsOpen(true)} 
        onNewChat={() => setMessages([])} 
      />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', maxWidth: 800, margin: '0 auto', padding: 20 }}>
        <h1 style={{ borderBottom: '2px solid #646cff', paddingBottom: 10, marginBottom: 16 }}>
          CScode
          <span style={{ fontSize: 14, color: '#666', marginLeft: 10 }}>
            AI Coding Assistant
          </span>
        </h1>

        <div style={{
          flex: 1,
          overflowY: 'auto',
          border: '1px solid #e0e0e0',
          borderRadius: 8,
          padding: 16,
          marginBottom: 16,
          background: '#ffffff',
        }}>
          {messages.length === 0 && (
            <p style={{ color: '#666', textAlign: 'center', marginTop: 40 }}>
              Start a conversation with CScode...
            </p>
          )}
          {messages.map((msg, i) => {
            const isLastLoading = i === messages.length - 1 && msg.role === 'assistant' && toolProgress && (msg.content === 'Thinking...' || msg.content.startsWith('🤔') || msg.content.startsWith('🔧'));
            const displayContent = isLastLoading && progressLogs.length > 0
              ? progressLogs.join('\n')
              : renderContent(msg.content);
            console.log('DEBUG message:', i, 'role:', msg.role, 'toolProgress:', toolProgress);
            return (
            <div key={i} style={{
              marginBottom: 12,
              textAlign: msg.role === 'user' ? 'right' : 'left',
            }}>
              <div style={{
                display: 'inline-block',
                padding: '8px 16px',
                borderRadius: 12,
                background: msg.role === 'user' ? '#646cff' : '#ffffff',
                color: msg.role === 'user' ? '#ffffff' : '#1a1a1a',
                fontWeight: msg.role === 'assistant' ? '500' : '400',
                maxWidth: '80%',
                whiteSpace: 'pre-wrap',
                lineHeight: '1.5',
                boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
                border: msg.role === 'assistant' ? '1px solid #e0e0e0' : 'none',
              }}>
                {displayContent}
              </div>
            </div>
            );
          })}
          <div ref={endRef} />
        </div>

        {toast && (
          <div style={{
            position: 'fixed', bottom: 80, left: '50%', transform: 'translateX(-50%)',
            padding: '10px 20px', borderRadius: 8, fontSize: 13, zIndex: 9999,
            background: toast.err ? '#f44336' : '#4caf50', color: '#fff',
            boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
          }}>
            {toast.msg}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="file"
            ref={fallbackInputRef}
            onChange={(e) => {
              if (e.target.files) {
                setAttachedFiles([...attachedFiles, ...Array.from(e.target.files)]);
              }
            }}
            style={{ display: 'none' }}
            multiple
          />
          <button
            onClick={handleAttachFile}
            style={{
              padding: '10px 16px',
              borderRadius: 8,
              border: '1px solid #ccc',
              background: '#fff',
              cursor: 'pointer',
              fontSize: 16,
            }}
            title="Attach files"
          >
            📎
          </button>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && sendMessage()}
            placeholder="Type your message..."
            disabled={loading}
            style={{
              flex: 1,
              padding: '10px 16px',
              borderRadius: 8,
              border: '1px solid #ccc',
              fontSize: 16,
              background: '#ffffff',
              color: '#1a1a1a',
            }}
          />
          <button
            onClick={loading ? handleStop : sendMessage}
            disabled={!loading && (!input.trim() && attachedFiles.length === 0)}
            style={{
              padding: '10px 24px',
              borderRadius: 8,
              border: 'none',
              background: loading ? '#e74c3c' : '#646cff',
              color: '#fff',
              fontSize: 16,
              cursor: (!loading && !input.trim() && attachedFiles.length === 0) ? 'not-allowed' : 'pointer',
              minWidth: 70,
            }}
            title={loading ? 'Stop' : 'Send'}
          >
            {loading ? '■' : 'Send'}
          </button>
        </div>

        {attachedFiles.length > 0 && (
          <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {attachedFiles.map((file, i) => (
              <div key={i} style={{
                padding: '4px 8px',
                background: '#e0e0e0',
                borderRadius: 4,
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}>
                {file.name}
                <button
                  onClick={() => {
                    setAttachedFiles(attachedFiles.filter((_, j) => j !== i));
                    if (fallbackInputRef.current) fallbackInputRef.current.value = '';
                  }}
                  style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 0 }}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 8, fontSize: 12, color: '#888' }}>
          Model: {config?.model || 'gpt-4o'} {config?.provider ? `(${config.provider})` : ''}
        </div>
      </div>

      <SettingsPanel isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

export default App;
