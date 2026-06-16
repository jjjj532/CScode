import { Filter, ArrowUpDown, Eye, Plus } from 'lucide-react';

export function ThreadsHeader() {
  return (
    <div className="flex items-center justify-between px-3 py-2 border-b border-v2-border">
      <span className="text-xs font-medium text-v2-text-muted tracking-wider">THREADS</span>
      <div className="flex items-center gap-1">
        <button className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors" title="Filter">
          <Filter size={14} />
        </button>
        <button className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors" title="Sort">
          <ArrowUpDown size={14} />
        </button>
        <button className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors" title="View">
          <Eye size={14} />
        </button>
        <button className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors" title="Add Project">
          <Plus size={14} />
        </button>
      </div>
    </div>
  );
}
