/** Light/dark theme — applied to <html data-theme> before paint (no flash) and
 *  toggled from the nav. Persisted to localStorage; falls back to the OS pref. */

export type Theme = 'light' | 'dark';
const KEY = 'audit-theme';

function read(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    /* private mode / no storage */
  }
  return typeof matchMedia !== 'undefined' && matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

function apply(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
}

/** Apply the persisted/OS theme synchronously at boot (before mount). */
export function applyBootTheme(): void {
  apply(read());
}

class ThemeStore {
  current = $state<Theme>('light');

  init(): void {
    this.current = read();
    apply(this.current);
  }

  toggle(): void {
    this.current = this.current === 'dark' ? 'light' : 'dark';
    try {
      localStorage.setItem(KEY, this.current);
    } catch {
      /* ignore */
    }
    apply(this.current);
  }
}

export const themeStore = new ThemeStore();
