import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SettingsPanel } from '../src/components/ui/SettingsPanel';

const mockConfig = Object.freeze({
  provider: 'openai' as const,
  model: 'gpt-4o' as const,
  api_base: null,
  api_key: '',
  max_tokens: 4096,
  temperature: 0.3,
  top_p: 1,
  system_prompt: null,
  mcp_servers: [],
  plugins: { enabled: [], settings: {} },
  keybindings: {},
});
const mockSetConfig = jest.fn();
const mockState = { config: mockConfig, setConfig: mockSetConfig };

jest.mock('../src/stores/useConfigStore', () => ({
  useConfigStore: (selector: any) => selector(mockState),
}));

jest.mock('../src/stores/useUIStore', () => ({
  useUIStore: (selector: any) => selector({
    setSettingsOpen: jest.fn(),
    theme: 'opencode-dark',
    setTheme: jest.fn(),
  }),
}));

jest.mock('../src/stores/useToastStore', () => ({
  useToastStore: (selector: any) => selector({
    addToast: jest.fn(),
  }),
}));

jest.mock('../src/lib/api', () => ({
  api: {
    config: { save: jest.fn() },
    permissionRules: { list: jest.fn().mockResolvedValue([]) },
  },
}));

describe('SettingsPanel Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders settings panel header', () => {
    render(<SettingsPanel />);
    const headers = screen.getAllByText(/settings/i);
    expect(headers.length).toBeGreaterThan(0);
  });

  test('renders close button', () => {
    render(<SettingsPanel />);
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  test('renders provider selector', () => {
    const { container } = render(<SettingsPanel />);
    const select = container.querySelector('select');
    expect(select).toBeTruthy();
  });

  test('renders model selector', () => {
    const { container } = render(<SettingsPanel />);
    const selects = container.querySelectorAll('select');
    expect(selects.length).toBeGreaterThanOrEqual(1);
  });

  test('renders API key input', () => {
    const { container } = render(<SettingsPanel />);
    const inputs = container.querySelectorAll('input[type="password"]');
    expect(inputs.length).toBeGreaterThanOrEqual(1);
  });

  test('API key input is password type', () => {
    render(<SettingsPanel />);
    const passwordInput = document.querySelector('input[type="password"]');
    expect(passwordInput).toBeTruthy();
  });

  test('renders temperature slider', () => {
    const { container } = render(<SettingsPanel />);
    const slider = container.querySelector('input[type="range"]');
    expect(slider).toBeTruthy();
  });

  test('renders save button', () => {
    render(<SettingsPanel />);
    const saveButton = screen.getByText(/save settings/i);
    expect(saveButton).toBeTruthy();
  });

  test('renders theme selector', () => {
    const { container } = render(<SettingsPanel />);
    const selects = container.querySelectorAll('select');
    expect(selects.length).toBeGreaterThanOrEqual(2);
  });

  test('loads current config values', () => {
    render(<SettingsPanel />);
    const modelSelect = screen.getByDisplayValue('gpt-4o');
    expect(modelSelect).toBeTruthy();
  });

  test('calls api.config.save when save is clicked', async () => {
    const { api } = require('../src/lib/api');
    api.config.save.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<SettingsPanel />);
    const saveButton = screen.getByText(/save settings/i);
    await user.click(saveButton);
    expect(api.config.save).toHaveBeenCalled();
  });
});
