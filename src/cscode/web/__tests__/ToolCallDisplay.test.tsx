import React from 'react';
import { render, screen } from '@testing-library/react';
import { ToolCallDisplay } from '../src/components/ui/ToolCallDisplay';

describe('ToolCallDisplay Component', () => {
  const defaultProps = {
    name: 'bash',
    args: 'echo hello',
    round: 1,
    max: 10,
    status: 'running' as const,
    stepLog: [],
  };

  test('expand toggle button has aria-label', () => {
    render(<ToolCallDisplay {...defaultProps} />);
    const toggle = screen.getByRole('button');
    expect(toggle).toHaveAttribute('aria-label');
  });
});
