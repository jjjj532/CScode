import { create } from 'zustand';

export interface Config {
  provider: string;
  model: string;
  api_base: string | null;
  api_key?: string;
  max_tokens: number;
  temperature: number;
  top_p: number;
  system_prompt: string | null;
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
