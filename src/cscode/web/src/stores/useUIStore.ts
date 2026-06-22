import { create } from 'zustand';
import type { ThemeId } from '../themes';

export type Mode = 'plan' | 'build';

interface UIState {
  theme: ThemeId;
  mode: Mode;
  sidebarOpen: boolean;
  settingsOpen: boolean;
  setTheme: (theme: ThemeId) => void;
  setMode: (mode: Mode) => void;
  toggleMode: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSettingsOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  theme: 'opencode-dark',
  mode: 'build',
  sidebarOpen: true,
  settingsOpen: false,
  setTheme: (theme) => set({ theme }),
  setMode: (mode) => set({ mode }),
  toggleMode: () => set((s) => ({ mode: s.mode === 'plan' ? 'build' : 'plan' })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setSettingsOpen: (open) => set({ settingsOpen: open }),
}));
