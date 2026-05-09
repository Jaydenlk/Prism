import { createContext, useCallback, useState, useEffect, type ReactNode } from 'react';

type Theme = 'light' | 'dark';
type Density = 'comfortable' | 'compact' | 'spacious';

interface ThemeState {
  theme: Theme;
  density: Density;
  setTheme: (t: Theme) => void;
  setDensity: (d: Density) => void;
  toggleTheme: () => void;
}

export const ThemeContext = createContext<ThemeState | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(
    () => (localStorage.getItem('prism_theme') as Theme) || 'light'
  );
  const [density, setDensityState] = useState<Density>(
    () => (localStorage.getItem('prism_density') as Density) || 'comfortable'
  );

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem('prism_theme', t);
    document.documentElement.setAttribute('data-theme', t);
  }, []);

  const setDensity = useCallback((d: Density) => {
    setDensityState(d);
    localStorage.setItem('prism_density', d);
    document.documentElement.setAttribute('data-density', d);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  }, [theme, setTheme]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-density', density);
  }, [theme, density]);

  return (
    <ThemeContext.Provider value={{ theme, density, setTheme, setDensity, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
