import { useState, useCallback, useEffect } from 'react';
import { useSessionStore } from '../../stores/useSessionStore';

interface QuestionItem {
  request_id: string;
  question: string;
  options: string[];
}

export function QuestionDialog() {
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const pendingQuestions = useSessionStore((s) => s.pendingQuestions);
  const dismissQuestion = useSessionStore((s) => s.dismissQuestion);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [customInputs, setCustomInputs] = useState<Record<string, string>>({});

  const current = activeSessionId ? pendingQuestions[activeSessionId] : undefined;

  // Reset state when questions change
  useEffect(() => {
    if (current) {
      const initial: Record<string, string[]> = {};
      const customInit: Record<string, string> = {};
      for (const q of current) {
        initial[q.request_id] = [];
        customInit[q.request_id] = '';
      }
      setAnswers(initial);
      setCustomInputs(customInit);
    }
  }, [current]);

  const handleToggleOption = useCallback((requestId: string, option: string) => {
    setAnswers((prev) => {
      const current = prev[requestId] || [];
      const exists = current.includes(option);
      return {
        ...prev,
        [requestId]: exists
          ? current.filter((a) => a !== option)
          : [...current, option],
      };
    });
  }, []);

  const handleCustomAnswer = useCallback((requestId: string, value: string) => {
    setCustomInputs((prev) => ({ ...prev, [requestId]: value }));
    setAnswers((prev) => ({
      ...prev,
      [requestId]: value.trim() ? [value.trim()] : [],
    }));
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!current || !activeSessionId) return;
    for (const q of current) {
      const answer = answers[q.request_id] || [];
      if (answer.length === 0) continue;
      try {
        await fetch(`/api/sessions/${activeSessionId}/questions/${q.request_id}/reply`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ answers: answer }),
        });
      } catch (e) {
        console.error('[QuestionDialog] reply failed', e);
      }
    }
    dismissQuestion(activeSessionId);
  }, [current, activeSessionId, answers, dismissQuestion]);

  const handleSkip = useCallback(async () => {
    if (!current || !activeSessionId) return;
    for (const q of current) {
      try {
        await fetch(`/api/sessions/${activeSessionId}/questions/${q.request_id}/reject`, {
          method: 'POST',
        });
      } catch (e) {
        console.error('[QuestionDialog] reject failed', e);
      }
    }
    dismissQuestion(activeSessionId);
  }, [current, activeSessionId, dismissQuestion]);

  if (!current || current.length === 0) return null;

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
      <div className="bg-v2-bg-base rounded-v2 shadow-v2-raised border border-v2-border w-full max-w-lg mx-4 p-5">
        <h3 className="text-sm font-semibold text-v2-text-primary mb-4">AI needs your input</h3>
        {current.map((q, qi) => (
          <div key={q.request_id} className="mb-4">
            <p className="text-sm text-v2-text-primary mb-2 font-medium">{q.question}</p>
            {q.options && q.options.length > 0 ? (
              <div className="space-y-1.5">
                {q.options.map((opt) => (
                  <label
                    key={opt}
                    className="flex items-center gap-2 px-3 py-1.5 bg-v2-bg-surface rounded-md cursor-pointer hover:bg-v2-bg-hover text-sm text-v2-text-primary"
                  >
                    <input
                      type="checkbox"
                      checked={(answers[q.request_id] || []).includes(opt)}
                      onChange={() => handleToggleOption(q.request_id, opt)}
                      className="accent-v2-accent"
                    />
                    {opt}
                  </label>
                ))}
              </div>
            ) : (
              <input
                type="text"
                value={customInputs[q.request_id] || ''}
                onChange={(e) => handleCustomAnswer(q.request_id, e.target.value)}
                placeholder="Type your answer..."
                className="w-full px-3 py-1.5 bg-v2-bg-surface border border-v2-border rounded-md text-sm text-v2-text-primary placeholder-v2-text-muted outline-none focus:border-v2-accent"
              />
            )}
          </div>
        ))}
        <div className="flex justify-end gap-2 mt-2">
          <button
            onClick={handleSkip}
            className="px-3 py-1.5 text-xs font-medium text-v2-text-secondary hover:text-v2-text-primary transition-colors"
          >
            Skip
          </button>
          <button
            onClick={handleSubmit}
            className="px-4 py-1.5 text-xs font-medium bg-v2-accent text-white rounded-md hover:opacity-90 transition-opacity"
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}
