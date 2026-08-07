import { useCallback } from 'react';
import { FolderOpen } from 'lucide-react';
import { useSessionStore } from '../../stores/useSessionStore';
import { useToastStore } from '../../stores/useToastStore';
import { isTauriRuntime, openOutputFile } from '../../lib/openOutputFile';

interface SessionFilesPanelProps {
  sessionId: string;
}

function fileNameOf(path: string): string {
  const parts = path.split('/');
  return parts[parts.length - 1] || path;
}

export function SessionFilesPanel({ sessionId }: SessionFilesPanelProps) {
  // No `|| []`: fresh array refs break zustand's Object.is snapshot compare → React #185 loop.
  const files = useSessionStore((s) => s.sessionFiles[sessionId]);
  const addToast = useToastStore((s) => s.addToast);

  const openFile = useCallback(async (path: string) => {
    try {
      const opened = await openOutputFile(path);
      if (!opened) {
        addToast(`路径已复制: ${path}`, 'success');
      }
    } catch (err) {
      addToast(`无法打开文件: ${err instanceof Error ? err.message : '未知错误'}`, 'error');
    }
  }, [addToast]);

  if (!files || files.length === 0) return null;

  return (
    <div className="flex gap-3 justify-start" data-testid="session-files-panel">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-accent/20 flex items-center justify-center mt-1">
        <FolderOpen size={16} className="text-v2-accent" />
      </div>
      <div className="max-w-[75%] items-start flex flex-col">
        <div className="rounded-v2 px-4 py-2.5 bg-v2-msg-assistant border border-v2-border-light text-v2-text-primary">
          <div className="text-xs font-medium mb-1 text-v2-accent">生成的文件</div>
          <ul className="space-y-1.5">
            {files.map((f) => (
              <li key={f} className="flex items-center gap-2">
                <span className="text-sm text-v2-text-primary truncate max-w-[300px]" title={f}>
                  📄 {fileNameOf(f)}
                </span>
                <button
                  onClick={() => openFile(f)}
                  aria-label={`打开 ${fileNameOf(f)}`}
                  className="text-[11px] px-2 py-0.5 rounded border border-v2-border-light text-v2-accent hover:bg-v2-accent/10 transition-colors shrink-0"
                  title={isTauriRuntime() ? '在 Finder 中显示' : '复制文件路径'}
                >
                  {isTauriRuntime() ? '在 Finder 中显示' : '复制路径'}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
