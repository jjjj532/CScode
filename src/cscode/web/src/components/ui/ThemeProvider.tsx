import { useEffect, type ReactNode } from 'react';
import { useUIStore } from '../../stores/useUIStore';
import { applyTheme } from '../../themes';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useUIStore((s) => s.theme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return <>{children}</>;
}
