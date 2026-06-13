import { useState, useRef, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { SettingsPanel } from './components/SettingsPanel';
import { useConfig } from './context/ConfigContext';
import { Message } from './types';

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const { currentSession, setCurrentSession, config, loadSessionMessages, createSession, loadSessions } = useConfig();

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleNewChat = async () => {
    // Clear messages first
    setMessages([]);
    // Create new session
    const id = await createSession('New Chat');
    // Set as current and don't load old messages (empty session)
    setCurrentSession(id);
  };

  const handleSessionClick = (sessionId: string) => {
    // Set current session - useEffect will load messages
    setCurrentSession(sessionId);
  };

  // Load messages when session changes
  useEffect(() => {
    console.log("Session changed to:", currentSession);
    if (currentSession) {
      loadSessionMessages(currentSession).then(msgs => {
        console.log("Loaded messages:", msgs.length);
        setMessages(msgs.map(m => ({ role: m.role as 'user' | 'assistant', content: m.content })));
      });
    } else {
      setMessages([]);
    }
  }, [currentSession]);

  const sendMessage = async () => {
    if ((!input.trim() && attachedFiles.length === 0) || loading) return;

    const textContent = input.trim();
    const userMsg: Message = { role: 'user', content: textContent || '(attached files)' };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

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

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers,
        body,
      });
      console.log('Response status:', res.status);
      const text = await res.text();
      console.log('Response text:', text);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${text}`);
      }
      const data = JSON.parse(text);
      const wasNewSession = !currentSession;
      setCurrentSession(data.session_id);
      if (wasNewSession) {
        // Refresh session list when a new session was auto-created
        loadSessions();
      }
      const assistantMsg: Message = { role: 'assistant', content: data.response };
      setMessages(prev => [...prev, assistantMsg]);
      setAttachedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      console.error('Chat error:', err);
      const errorMsg: Message = { role: 'assistant', content: 'Error: ' + String(err) };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
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
          background: '#fafafa',
        }}>
          {messages.length === 0 && (
            <p style={{ color: '#999', textAlign: 'center', marginTop: 40 }}>
              Start a conversation with CScode...
            </p>
          )}
          {messages.map((msg, i) => (
            <div key={i} style={{
              marginBottom: 12,
              textAlign: msg.role === 'user' ? 'right' : 'left',
            }}>
              <div style={{
                display: 'inline-block',
                padding: '8px 16px',
                borderRadius: 12,
                background: msg.role === 'user' ? '#646cff' : '#e0e0e0',
                color: msg.role === 'user' ? '#fff' : '#000',
                maxWidth: '80%',
                whiteSpace: 'pre-wrap',
              }}>
                {msg.content}
              </div>
            </div>
          ))}
          <div ref={endRef} />
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="file"
            ref={fileInputRef}
            onChange={(e) => {
              if (e.target.files) {
                setAttachedFiles([...attachedFiles, ...Array.from(e.target.files)]);
              }
            }}
            style={{ display: 'none' }}
            multiple
          />
          <button
            onClick={() => fileInputRef.current?.click()}
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
            }}
          />
          <button
            onClick={sendMessage}
            disabled={loading || (!input.trim() && attachedFiles.length === 0)}
            style={{
              padding: '10px 24px',
              borderRadius: 8,
              border: 'none',
              background: loading ? '#ccc' : '#646cff',
              color: '#fff',
              fontSize: 16,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? '...' : 'Send'}
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
                    if (fileInputRef.current) fileInputRef.current.value = '';
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
