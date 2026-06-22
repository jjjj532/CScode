import { X, CheckCircle, AlertCircle, Info } from 'lucide-react';
import { useToastStore, type ToastItem } from '../../stores/useToastStore';

function ToastIcon({ type }: { type: ToastItem['type'] }) {
  switch (type) {
    case 'success':
      return <CheckCircle size={16} className="text-green-400" />;
    case 'error':
      return <AlertCircle size={16} className="text-red-400" />;
    case 'info':
      return <Info size={16} className="text-v2-accent" />;
  }
}

function ToastItem({ toast }: { toast: ToastItem }) {
  const removeToast = useToastStore((s) => s.removeToast);

  const bgClass = toast.type === 'error'
    ? 'bg-red-500/10 border-red-500/30'
    : toast.type === 'success'
      ? 'bg-green-500/10 border-green-500/30'
      : 'bg-v2-bg-deep border-v2-border';

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 rounded-v2 border shadow-lg text-sm ${bgClass} animate-in slide-in-from-bottom-2 transition-all`}
      role="alert"
    >
      <ToastIcon type={toast.type} />
      <span className="text-v2-text-primary flex-1">{toast.message}</span>
      <button onClick={() => removeToast(toast.id)} className="text-v2-text-muted hover:text-v2-text-secondary">
        <X size={14} />
      </button>
    </div>
  );
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-[100] flex flex-col gap-2 min-w-[300px] max-w-[500px]">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  );
}
