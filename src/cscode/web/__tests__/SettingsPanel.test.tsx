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

const mockPermissionRules = jest.fn().mockResolvedValue([]);

jest.mock('../src/lib/api', () => ({
  api: {
    config: { save: jest.fn() },
    permissionRules: {
      list: (...args: unknown[]) => mockPermissionRules(...args),
      create: jest.fn(),
      delete: jest.fn(),
    },
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

  // ─── Permission Rules ───────────────────────────────────────────────

  test('renders permission rules section heading', () => {
    mockPermissionRules.mockResolvedValue([]);
    render(<SettingsPanel />);
    expect(screen.getByText(/Permission Rules/i)).toBeTruthy();
  });

  test('shows empty state when no rules', async () => {
    mockPermissionRules.mockResolvedValue([]);
    render(<SettingsPanel />);
    expect(await screen.findByText(/No saved permission rules/i)).toBeTruthy();
  });

  test('renders permission rules from API with action/resource/effect', async () => {
    mockPermissionRules.mockResolvedValue([
      { id: 1, action: 'bash', resource: '*', effect: 'deny' },
      { id: 2, action: 'read', resource: '/tmp/*', effect: 'allow' },
    ]);
    render(<SettingsPanel />);
    expect(await screen.findByText('bash')).toBeTruthy();
    expect(await screen.findByText('read')).toBeTruthy();
    expect(await screen.findByText('/tmp/*')).toBeTruthy();
    const denyEls = screen.getAllByText((_, el) => el.textContent === 'Denied');
    expect(denyEls.length).toBeGreaterThanOrEqual(1);
  });

  test('delete button calls api.permissionRules.delete with numeric id', async () => {
    const { api } = require('../src/lib/api');
    api.permissionRules.delete.mockResolvedValue(undefined);
    mockPermissionRules.mockResolvedValue([
      { id: 42, action: 'bash', resource: '*', effect: 'deny' },
    ]);
    render(<SettingsPanel />);
    const deleteBtn = await screen.findByLabelText('Delete rule');
    const user = userEvent.setup();
    await user.click(deleteBtn);
    expect(api.permissionRules.delete).toHaveBeenCalledWith(42);
  });

  test('shows create rule form inputs', async () => {
    mockPermissionRules.mockResolvedValue([]);
    render(<SettingsPanel />);
    const actionInput = screen.getByPlaceholderText(/^action$/i);
    const resourceInput = screen.getByPlaceholderText(/^resource$/i);
    const effectSelect = screen.getByLabelText(/Effect/i);
    expect(actionInput).toBeTruthy();
    expect(resourceInput).toBeTruthy();
    expect(effectSelect).toBeTruthy();
  });

  test('calls api.permissionRules.create with action/resource/effect', async () => {
    const { api } = require('../src/lib/api');
    api.permissionRules.create.mockResolvedValue({ id: 99 });
    mockPermissionRules.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<SettingsPanel />);

    await user.type(screen.getByPlaceholderText(/^action$/i), 'write');
    await user.type(screen.getByPlaceholderText(/^resource$/i), '/data/*');
    await user.click(screen.getByLabelText(/Add rule/i));

    expect(api.permissionRules.create).toHaveBeenCalledWith({
      action: 'write',
      resource: '/data/*',
      effect: 'deny',
    });
  });
});
