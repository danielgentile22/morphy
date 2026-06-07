/**
 * Appearance resolution (PRD #121) — pure + DOM-free, so it unit-tests cleanly.
 *
 * Decides the *effective* theme from a user preference plus the OS dark-mode
 * flag, and the document attributes to apply. Theme and colorblind mode are
 * independent switches, so any combination composes (dark+cb, light+cb, either
 * alone). The store + the flash-free boot both route through here, so the
 * attribute/class names live in exactly one place.
 */

export type ThemePref = 'light' | 'dark' | 'system';
export type EffectiveTheme = 'light' | 'dark';

/** Set on `<html>`: `data-theme="light|dark"`, plus the colorblind class. */
export const THEME_ATTR = 'data-theme';
export const COLORBLIND_CLASS = 'cb';

/** A bare preference + the OS flag → the theme actually painted. An explicit
 *  light/dark wins; anything else (including `system` or a stale/garbage value)
 *  follows the OS. */
export function resolveEffectiveTheme(pref: ThemePref, systemPrefersDark: boolean): EffectiveTheme {
  if (pref === 'dark') return 'dark';
  if (pref === 'light') return 'light';
  return systemPrefersDark ? 'dark' : 'light';
}

export interface Appearance {
  /** value for `data-theme` on `<html>` */
  theme: EffectiveTheme;
  /** whether the `.cb` colorblind class is present on `<html>` */
  colorblind: boolean;
}

export function resolveAppearance(
  pref: ThemePref,
  systemPrefersDark: boolean,
  colorblind: boolean,
): Appearance {
  return { theme: resolveEffectiveTheme(pref, systemPrefersDark), colorblind };
}

/** Apply an appearance to the document root. A no-op when there's no DOM (e.g. a
 *  unit test that didn't pass a root). Centralising the attribute/class names
 *  here keeps the store and the boot snippet from drifting apart. */
export function applyAppearance(a: Appearance, root?: HTMLElement): void {
  const el = root ?? (typeof document !== 'undefined' ? document.documentElement : null);
  if (!el) return;
  el.setAttribute(THEME_ATTR, a.theme);
  el.classList.toggle(COLORBLIND_CLASS, a.colorblind);
}
