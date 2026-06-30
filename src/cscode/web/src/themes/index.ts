export type ThemeId = 'opencode-dark' | 'opencode-light' | 'catppuccin' | 'dracula' | 'github-dark' | 'github-light';

export interface Theme {
  id: ThemeId;
  name: string;
  type: 'dark' | 'light';
}

export const themes: Theme[] = [
  { id: 'opencode-dark', name: 'OpenCode Dark', type: 'dark' },
  { id: 'opencode-light', name: 'OpenCode Light', type: 'light' },
  { id: 'catppuccin', name: 'Catppuccin', type: 'dark' },
  { id: 'dracula', name: 'Dracula', type: 'dark' },
  { id: 'github-dark', name: 'GitHub Dark', type: 'dark' },
  { id: 'github-light', name: 'GitHub Light', type: 'light' },
];

export function applyTheme(themeId: ThemeId): void {
  try {
    document.documentElement.setAttribute('data-theme', themeId);
  } catch {
    // Silently ignore — document may not be available (SSR, test env)
  }
}
