/**
 * EmptyState Tests
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { EmptyState } from '../src/components/ui/EmptyState';

describe('EmptyState', () => {
  test('renders default empty state', () => {
    render(<EmptyState />);
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
  });

  test('renders with icon', () => {
    render(<EmptyState icon="📭" />);
    expect(screen.getByText('📭')).toBeInTheDocument();
  });

  test('renders title', () => {
    render(<EmptyState title="No sessions" />);
    expect(screen.getByText('No sessions')).toBeInTheDocument();
  });

  test('renders description', () => {
    render(<EmptyState description="Create a session to get started" />);
    expect(screen.getByText('Create a session to get started')).toBeInTheDocument();
  });

  test('renders action button with label', () => {
    render(<EmptyState actionLabel="New Session" />);
    expect(screen.getByRole('button', { name: 'New Session' })).toBeInTheDocument();
  });

  test('calls onAction when action button clicked', () => {
    const onAction = jest.fn();
    render(<EmptyState actionLabel="Create" onAction={onAction} />);
    screen.getByRole('button', { name: 'Create' }).click();
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  test('does not render action button when no label', () => {
    render(<EmptyState />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  test('renders compact variant', () => {
    const { container } = render(<EmptyState variant="compact" title="Empty" />);
    expect(container.firstChild).toHaveClass('py-8');
  });

  test('renders full variant with larger spacing', () => {
    const { container } = render(<EmptyState variant="full" title="Empty" />);
    expect(container.firstChild).toHaveClass('py-16');
  });

  test('renders with accessible role', () => {
    render(<EmptyState title="Nothing here" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
