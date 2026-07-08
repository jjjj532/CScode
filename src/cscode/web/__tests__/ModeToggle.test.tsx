import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModeToggle } from '../src/components/ui/ModeToggle';

jest.mock('../src/stores/useUIStore', () => {
  const state = { mode: 'plan', toggleMode: jest.fn() };
  const setMode = jest.fn((m: string) => { state.mode = m; });
  return {
    __esModule: true,
    useUIStore: (selector: any) => selector({
      get mode() { return state.mode; },
      setMode,
      toggleMode: state.toggleMode,
    }),
  };
});

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

  test('clicking Build switches aria-checked from Plan to Build', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<ModeToggle />);
    const planRadio = screen.getByRole('radio', { name: /plan/i });
    const buildRadio = screen.getByRole('radio', { name: /build/i });
    expect(planRadio).toHaveAttribute('aria-checked', 'true');
    expect(buildRadio).toHaveAttribute('aria-checked', 'false');
    await user.click(buildRadio);
    rerender(<ModeToggle />);
    expect(planRadio).toHaveAttribute('aria-checked', 'false');
    expect(buildRadio).toHaveAttribute('aria-checked', 'true');
  });

  test('clicking Plan maintains aria-checked on Plan', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<ModeToggle />);
    const planRadio = screen.getByRole('radio', { name: /plan/i });
    await user.click(planRadio);
    rerender(<ModeToggle />);
    expect(planRadio).toHaveAttribute('aria-checked', 'true');
  });

  test('displays mode labels', () => {
    render(<ModeToggle />);
    expect(screen.getByText('Plan')).toBeTruthy();
    expect(screen.getByText('Build')).toBeTruthy();
  });
});
