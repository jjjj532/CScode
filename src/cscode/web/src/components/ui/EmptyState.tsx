import React from 'react';

interface EmptyStateProps {
  icon?: string;
  title?: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  variant?: 'compact' | 'full';
}

export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  variant = 'compact',
}: EmptyStateProps) {
  const padding = variant === 'full' ? 'py-16' : 'py-8';

  return (
    <div
      data-testid="empty-state"
      role="status"
      className={`flex flex-col items-center justify-center ${padding} px-4 text-center`}
    >
      {icon && <span className="text-3xl mb-3" aria-hidden="true">{icon}</span>}
      {title && (
        <h3 className="text-lg font-medium text-v2-text-primary mb-1">{title}</h3>
      )}
      {description && (
        <p className="text-sm text-v2-text-secondary max-w-xs">{description}</p>
      )}
      {actionLabel && (
        <button
          type="button"
          onClick={onAction}
          className="mt-4 px-4 py-2 text-sm font-medium rounded-lg bg-v2-accent text-white hover:opacity-90 transition-opacity"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
