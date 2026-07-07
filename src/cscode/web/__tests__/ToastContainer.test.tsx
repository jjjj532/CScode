import React from 'react';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToastContainer } from '../src/components/ui/ToastContainer';

const mockToasts = [
  { id: '1', type: 'success', message: 'Success message' },
  { id: '2', type: 'error', message: 'Error message' },
  { id: '3', type: 'info', message: 'Info message' },
];

const mockRemoveToast = jest.fn();
const mockAddToast = jest.fn();

jest.mock('../src/stores/useToastStore', () => ({
  useToastStore: (selector: any) => selector({
    toasts: mockToasts,
    addToast: mockAddToast,
    removeToast: mockRemoveToast,
  }),
}));

describe('ToastContainer Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders toasts', () => {
    render(<ToastContainer />);
    expect(screen.getByText('Success message')).toBeTruthy();
    expect(screen.getByText('Error message')).toBeTruthy();
    expect(screen.getByText('Info message')).toBeTruthy();
  });

  test('renders close button for each toast', () => {
    render(<ToastContainer />);
    const closeButtons = screen.getAllByRole('button');
    expect(closeButtons.length).toBe(3);
  });

  test('calls removeToast when close button is clicked', async () => {
    const user = userEvent.setup();
    render(<ToastContainer />);
    const closeButtons = screen.getAllByRole('button');
    await user.click(closeButtons[0]);
    expect(mockRemoveToast).toHaveBeenCalledWith('1');
  });

  test('close buttons have aria-label for accessibility', () => {
    render(<ToastContainer />);
    const closeButtons = screen.getAllByRole('button');
    closeButtons.forEach((btn) => {
      expect(btn).toHaveAttribute('aria-label');
    });
  });
});
