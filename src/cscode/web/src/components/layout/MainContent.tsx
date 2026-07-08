import { useState } from 'react';
import { Terminal } from 'lucide-react';
import { MessageList } from '../chat/MessageList';
import { Composer } from '../chat/Composer';
import { QuestionDialog } from '../ui/QuestionDialog';
import { PtyTerminal } from '../PtyTerminal';

export function MainContent() {
  const [showPty, setShowPty] = useState(false);

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-v2-bg-base m-2 mr-2 mb-2 rounded-v2 shadow-v2-raised overflow-hidden" role="main">
      <MessageList />
      <Composer />
      <QuestionDialog />
      {showPty && <PtyTerminal />}
      <button
        onClick={() => setShowPty((v) => !v)}
        title={showPty ? 'Close terminal' : 'Open terminal'}
        style={{
          position: 'absolute',
          bottom: 8,
          right: 8,
          width: 32,
          height: 32,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: showPty ? '#3b4261' : '#1f2335',
          border: '1px solid #2c2c2c',
          borderRadius: 6,
          color: '#a9b1d6',
          cursor: 'pointer',
          zIndex: 50,
        }}
      >
        <Terminal size={16} />
      </button>
    </div>
  );
}
