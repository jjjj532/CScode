/**
 * Skeleton Component Tests
 * Tests for animated loading placeholder components
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { Skeleton, SkeletonText, SkeletonList } from '../src/components/ui/Skeleton';

describe('Skeleton Component', () => {
  test('renders with role="status" for accessibility', () => {
    render(<Skeleton />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  test('has aria-label for screen readers', () => {
    render(<Skeleton />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Loading');
  });

  test('has animate-pulse class for animation', () => {
    render(<Skeleton />);
    expect(screen.getByRole('status')).toHaveClass('animate-pulse');
  });

  test('applies custom className', () => {
    render(<Skeleton className="h-10 w-full" />);
    const el = screen.getByRole('status');
    expect(el).toHaveClass('h-10');
    expect(el).toHaveClass('w-full');
  });

  test('has default height and width classes', () => {
    render(<Skeleton />);
    const el = screen.getByRole('status');
    expect(el).toHaveClass('h-4');
    expect(el).toHaveClass('w-full');
  });

  test('rounded-md class for consistent border radius', () => {
    render(<Skeleton />);
    expect(screen.getByRole('status')).toHaveClass('rounded-md');
  });
});

describe('SkeletonText Component', () => {
  test('renders specified number of lines', () => {
    render(<SkeletonText lines={3} />);
    const lines = screen.getAllByRole('status');
    expect(lines).toHaveLength(3);
  });

  test('defaults to 3 lines', () => {
    render(<SkeletonText />);
    const lines = screen.getAllByRole('status');
    expect(lines).toHaveLength(3);
  });

  test('last line is shorter for text-like appearance', () => {
    render(<SkeletonText lines={3} />);
    const lines = screen.getAllByRole('status');
    expect(lines[2]).toHaveClass('w-3/4');
  });

  test('first lines are full width', () => {
    render(<SkeletonText lines={2} />);
    const lines = screen.getAllByRole('status');
    expect(lines[0]).toHaveClass('w-full');
  });
});

describe('SkeletonList Component', () => {
  test('renders specified number of items', () => {
    render(<SkeletonList count={4} />);
    const items = screen.getAllByTestId('skeleton-list-item');
    expect(items).toHaveLength(4);
  });

  test('defaults to 5 items', () => {
    render(<SkeletonList />);
    const items = screen.getAllByTestId('skeleton-list-item');
    expect(items).toHaveLength(5);
  });

  test('each item contains skeleton elements', () => {
    render(<SkeletonList count={2} />);
    const items = screen.getAllByTestId('skeleton-list-item');
    items.forEach((item) => {
      const skeletons = item.querySelectorAll('[role="status"]');
      expect(skeletons.length).toBeGreaterThanOrEqual(1);
    });
  });

  test('renders with container role', () => {
    render(<SkeletonList count={1} />);
    expect(screen.getByRole('list')).toBeInTheDocument();
  });
});
