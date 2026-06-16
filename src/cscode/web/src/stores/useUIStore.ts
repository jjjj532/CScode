import { create } from 'zustand';
import type { ThemeId } from '../themes';

export type Mode = 'plan' | 'build';

interface UIState {
  theme: ThemeId;
  mode: Mode;
  sidebarOpen: boolean;
  settingsOpen: boolean;
  attachedFiles: File[];
  setTheme: (theme: ThemeId) => void;
  setMode: (mode: Mode) => void;
  toggleMode: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSettingsOpen: (open: boolean) => void;
  setAttachedFiles: (files: File[]) => void;
  addAttachedFile: (file: File) => void;
  removeAttachedFile: (index: number) => void;
}

export const useUIStore = create<UIState>((set) => ({
  theme: 'opencode-dark',
  mode: 'build',
  sidebarOpen: true,
  settingsOpen: false,
  attachedFiles: [],
  setTheme: (theme) => set({ theme }),
  setMode: (mode) => set({ mode }),
  toggleMode: () => set((s) => ({ mode: s.mode === 'plan' ? 'build' : 'plan' })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setSettingsOpen: (open) => set({ settingsOpen: open }),
  setAttachedFiles: (files) => set({ attachedFiles: files }),
  addAttachedFile: (file) => set((s) => ({ attachedFiles: [...s.attachedFiles, file] })),
  removeAttachedFile: (index) => set((s) => ({ attachedFiles: s.attachedFiles.filter((_, i) => i !== index) })),
}));
