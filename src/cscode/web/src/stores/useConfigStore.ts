import { create } from 'zustand';

export interface McpServerConfig {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  enabled: boolean;
}

export interface PluginConfig {
  enabled: string[];
  settings: Record<string, Record<string, unknown>>;
}

export interface PermissionRule {
  pattern: string;
  allow: boolean;
}

export interface Config {
  provider: string;
  model: string;
  api_base: string | null;
  api_key?: string;
  api_key_configured?: boolean;
  max_tokens: number;
  temperature: number;
  top_p: number;
  system_prompt: string | null;
  theme?: string;
  mcp_servers?: McpServerConfig[];
  plugins?: PluginConfig;
  permission_rules?: PermissionRule[];
  keybindings?: Record<string, string>;
}

interface ConfigState {
  config: Config | null;
  loading: boolean;
  setConfig: (config: Config) => void;
  updateConfig: (partial: Partial<Config>) => void;
  setLoading: (loading: boolean) => void;
}

export const useConfigStore = create<ConfigState>((set) => ({
  config: null,
  loading: false,
  setConfig: (config) => set({ config }),
  updateConfig: (partial) => set((s) => ({ config: s.config ? { ...s.config, ...partial } : null })),
  setLoading: (loading) => set({ loading }),
}));
