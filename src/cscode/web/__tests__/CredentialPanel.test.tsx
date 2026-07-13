import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { CredentialPanel } from '../src/components/CredentialPanel';

jest.mock('../src/stores/useToastStore', () => ({
  useToastStore: (selector: any) => selector({
    addToast: jest.fn(),
  }),
}));

// Mock global fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

describe('CredentialPanel Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ credentials: [] }),
    });
  });

  test('renders credential panel header', () => {
    render(<CredentialPanel />);
    expect(screen.getByText('Credentials')).toBeTruthy();
  });

  test('password input is inside a form element', () => {
    const { container } = render(<CredentialPanel />);
    const forms = container.querySelectorAll('form');
    expect(forms.length).toBeGreaterThanOrEqual(1);
    const passwordInput = container.querySelector('input[type="password"]');
    expect(passwordInput).toBeTruthy();
    // The password input should be inside a form
    const form = passwordInput?.closest('form');
    expect(form).toBeTruthy();
  });

  test('password input has autocomplete attribute', () => {
    const { container } = render(<CredentialPanel />);
    const passwordInput = container.querySelector('input[type="password"]');
    expect(passwordInput).toBeTruthy();
    expect(passwordInput?.getAttribute('autocomplete')).toBe('off');
  });

  test('renders provider selector', () => {
    const { container } = render(<CredentialPanel />);
    expect(container.querySelector('select')).toBeTruthy();
  });

  test('renders add button', () => {
    render(<CredentialPanel />);
    expect(screen.getByText('Add')).toBeTruthy();
  });

  test('renders credentials list when empty', () => {
    render(<CredentialPanel />);
    expect(screen.getByText('No saved credentials')).toBeTruthy();
  });
});
