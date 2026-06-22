import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModeToggle } from '../src/components/ui/ModeToggle';

const mockSetMode = jest.fn();

jest.mock('../src/stores/useUIStore', () => ({
  useUIStore: (selector: any) => selector({
    mode: 'plan',
    setMode: mockSetMode,
    toggleMode: jest.fn(),
  }),
}));

describe('ModeToggle Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders Plan mode radio', () => {
    render(<ModeToggle />);
    const planRadio = screen.getByRole('radio', { name: /plan/i });
    expect(planRadio).toBeTruthy();
  });

  test('renders Build mode radio', () => {
    render(<ModeToggle />);
    const buildRadio = screen.getByRole('radio', { name: /build/i });
    expect(buildRadio).toBeTruthy();
  });

  test('highlights active mode', () => {
    const { container } = render(<ModeToggle />);
    const checkedRadio = container.querySelector('[aria-checked="true"]');
    expect(checkedRadio).toBeTruthy();
    expect(checkedRadio?.textContent).toBe('Plan');
  });

  test('calls setMode when Plan is clicked', async () => {
    const user = userEvent.setup();
    render(<ModeToggle />);
    const planRadio = screen.getByRole('radio', { name: /plan/i });
    await user.click(planRadio);
    expect(mockSetMode).toHaveBeenCalledWith('plan');
  });

  test('calls setMode when Build is clicked', async () => {
    const user = userEvent.setup();
    render(<ModeToggle />);
    const buildRadio = screen.getByRole('radio', { name: /build/i });
    await user.click(buildRadio);
    expect(mockSetMode).toHaveBeenCalledWith('build');
  });

  test('displays mode labels', () => {
    render(<ModeToggle />);
    expect(screen.getByText('Plan')).toBeTruthy();
    expect(screen.getByText('Build')).toBeTruthy();
  });
});
