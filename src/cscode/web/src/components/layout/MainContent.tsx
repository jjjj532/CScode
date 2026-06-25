import { MessageList } from '../chat/MessageList';
import { Composer } from '../chat/Composer';
import { QuestionDialog } from '../ui/QuestionDialog';

export function MainContent() {
  return (
    <div className="flex-1 flex flex-col min-w-0 bg-v2-bg-base m-2 mr-2 mb-2 rounded-v2 shadow-v2-raised overflow-hidden" role="main">
      <MessageList />
      <Composer />
      <QuestionDialog />
    </div>
  );
}
