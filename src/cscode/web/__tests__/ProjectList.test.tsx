/**
 * ProjectList Tests
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { ProjectList } from '../src/components/sidebar/ProjectList';

const defaultProps = {
  sessions: [] as any[],
  activeSessionId: null,
  onSelectSession: jest.fn(),
  onDeleteSession: jest.fn(),
  onUpdateSession: jest.fn(),
  onImportSession: jest.fn(),
};

describe('ProjectList', () => {
  test('renders empty state when no sessions', () => {
    render(<ProjectList {...defaultProps} />);
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    expect(screen.getByText('No sessions yet')).toBeInTheDocument();
  });

  test('renders session items when sessions exist', () => {
    render(
      <ProjectList
        {...defaultProps}
        sessions={[{ id: 's1', title: 'Chat 1' } as any]}
      />
    );
    expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument();
  });
});
