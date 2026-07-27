import React from 'react';
import { render, screen } from '@testing-library/react';
import { OfflineBanner } from '../src/components/ui/OfflineBanner';

// Mock the hook
const mockUseOnlineStatus = jest.fn();
jest.mock('../src/hooks/useOnlineStatus', () => ({
  useOnlineStatus: () => mockUseOnlineStatus(),
}));

describe('OfflineBanner Component', () => {
  beforeEach(() => {
    mockUseOnlineStatus.mockReturnValue(true);
  });

  test('returns null when online', () => {
    const { container } = render(<OfflineBanner />);
    expect(container.innerHTML).toBe('');
  });

  test('renders banner when offline', () => {
    mockUseOnlineStatus.mockReturnValue(false);
    render(<OfflineBanner />);
    expect(screen.getByText('You are offline')).toBeInTheDocument();
    expect(screen.getByText(/Some features may be unavailable/)).toBeInTheDocument();
  });

  test('banner has role="alert" for accessibility', () => {
    mockUseOnlineStatus.mockReturnValue(false);
    render(<OfflineBanner />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  test('banner has warning styling classes', () => {
    mockUseOnlineStatus.mockReturnValue(false);
    render(<OfflineBanner />);
    const banner = screen.getByRole('alert');
    expect(banner.className).toContain('yellow');
  });
});
