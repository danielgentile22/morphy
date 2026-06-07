import { describe, it, expect } from 'vitest';
import {
  resolveEffectiveTheme,
  resolveAppearance,
  type ThemePref,
} from '../../src/lib/appearance';

describe('appearance resolution (PRD #121)', () => {
  it('resolves system theme from the OS dark-mode flag', () => {
    expect(resolveEffectiveTheme('system', true)).toBe('dark');
    expect(resolveEffectiveTheme('system', false)).toBe('light');
  });

  it('honours an explicit theme regardless of the OS flag', () => {
    expect(resolveEffectiveTheme('dark', false)).toBe('dark');
    expect(resolveEffectiveTheme('dark', true)).toBe('dark');
    expect(resolveEffectiveTheme('light', true)).toBe('light');
    expect(resolveEffectiveTheme('light', false)).toBe('light');
  });

  it('composes colorblind independently with each theme', () => {
    // theme and colorblind are orthogonal switches — every combination is valid
    expect(resolveAppearance('dark', false, true)).toEqual({ theme: 'dark', colorblind: true });
    expect(resolveAppearance('light', false, true)).toEqual({ theme: 'light', colorblind: true });
    expect(resolveAppearance('dark', false, false)).toEqual({ theme: 'dark', colorblind: false });
    expect(resolveAppearance('system', true, false)).toEqual({ theme: 'dark', colorblind: false });
    expect(resolveAppearance('system', false, true)).toEqual({ theme: 'light', colorblind: true });
  });

  it('treats an unknown preference as system (defensive)', () => {
    expect(resolveEffectiveTheme('bogus' as ThemePref, true)).toBe('dark');
    expect(resolveEffectiveTheme('bogus' as ThemePref, false)).toBe('light');
  });
});
