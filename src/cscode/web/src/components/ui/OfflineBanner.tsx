import { WifiOff } from 'lucide-react';
import { useOnlineStatus } from '../../hooks/useOnlineStatus';

export function OfflineBanner() {
  const isOnline = useOnlineStatus();

  if (isOnline) return null;

  return (
    <div
      role="alert"
      className="flex items-center justify-center gap-2 px-4 py-2 bg-yellow-500/10 border-b border-yellow-500/30 text-yellow-600 text-sm"
    >
      <WifiOff size={14} />
      <span className="font-medium">You are offline</span>
      <span className="text-yellow-500/70">— Some features may be unavailable</span>
    </div>
  );
}
