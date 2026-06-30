import { useEffect, type ReactNode } from 'react';
import { useUIStore } from '../../stores/useUIStore';
import { useConfigStore } from '../../stores/useConfigStore';
import { applyTheme } from '../../themes';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useUIStore((s) => s.theme);
  const config = useConfigStore((s) => s.config);
  const setTheme = useUIStore((s) => s.setTheme);

  // Load persisted theme on mount
  useEffect(() => {
    if (config?.theme && config.theme !== theme) {
      setTheme(config.theme as any);
    }
  }, []);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return <>{children}</>;
}
