// Per-user preferences store (PRD #121) — the first per-user persisted layer.
//
// Loads /api/me/settings, exposes the typed prefs reactively, persists via PUT,
// and applies appearance through the pure `appearance.ts` resolver. Mirrors the
// singleton-class + $state pattern of the other stores (scoring, leads).
//
// Flash-free boot: the *effective* appearance is cached in localStorage and
// applied synchronously before the app mounts (see `applyBootAppearance`); the
// backend value is the source of truth and reconciles once settings load.

import { fetchMySettings, saveMySettings, ApiError, type UserSettings } from './leads-api';
import { auth } from './auth-store.svelte';
import { resolveAppearance, applyAppearance, type ThemePref, type Appearance } from './appearance';
import { parseMapView, type BasemapName, type MapView } from './basemap';

const APPEARANCE_CACHE_KEY = 'settings.appearance';

const DEFAULTS: UserSettings = {
  theme: 'system',
  colorblind: false,
  // Satellite (MapTiler) is the default — aerial imagery shows the actual tower
  // site/land out of the box. Degrades to Carto Dark when no MapTiler key is
  // built in (so it never 403s); the other basemaps stay selectable.
  basemap: 'satellite',
  view_mode: 'last',
  home_view: '',
  filter_default: '',
  filter_default_apply: false,
};

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : false;
}

function readCachedAppearance(): Appearance | null {
  try {
    const raw = localStorage.getItem(APPEARANCE_CACHE_KEY);
    if (!raw) return null;
    const v: unknown = JSON.parse(raw);
    if (v && typeof v === 'object') {
      const o = v as Record<string, unknown>;
      if ((o.theme === 'light' || o.theme === 'dark') && typeof o.colorblind === 'boolean') {
        return { theme: o.theme, colorblind: o.colorblind };
      }
    }
  } catch {
    // unreadable cache — ignore
  }
  return null;
}

function writeCachedAppearance(a: Appearance): void {
  try {
    localStorage.setItem(APPEARANCE_CACHE_KEY, JSON.stringify(a));
  } catch {
    // storage disabled — the theme just isn't cached for the next boot
  }
}

/** Apply the cached appearance synchronously at boot, before the app mounts, so
 *  there's no flash of the wrong theme. With no cache yet (a first-ever load),
 *  follow the OS. The backend value reconciles once `load()` resolves. */
export function applyBootAppearance(): void {
  const cached = readCachedAppearance();
  applyAppearance(cached ?? { theme: systemPrefersDark() ? 'dark' : 'light', colorblind: false });
}

class UserSettingsStore {
  settings = $state<UserSettings>({ ...DEFAULTS });
  loaded = $state(false);
  saving = $state(false);
  error = $state<string | null>(null);
  // Reactive mirror of the OS dark-mode flag so `system` theme re-resolves live.
  systemDark = $state(systemPrefersDark());
  private watching = false;

  get theme(): ThemePref {
    return this.settings.theme;
  }
  get colorblind(): boolean {
    return this.settings.colorblind;
  }
  get basemap(): BasemapName {
    return this.settings.basemap;
  }
  get appearance(): Appearance {
    return resolveAppearance(this.settings.theme, this.systemDark, this.settings.colorblind);
  }
  /** The pinned home view, or null when unset/malformed. */
  get homeView(): MapView | null {
    return parseMapView(this.settings.home_view);
  }

  /** Load the signed-in user's prefs and reconcile appearance. Call once the
   *  session is verified. */
  async load(): Promise<void> {
    this.watchSystemTheme();
    try {
      this.settings = await fetchMySettings();
      this.loaded = true;
      this.apply();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) auth.signOut();
      // otherwise keep the boot defaults (already applied) — the app still works
    }
  }

  /** Upsert one or more prefs. Optimistic: the local state + appearance update
   *  immediately so the UI feels responsive; a failed PUT reverts them (so the
   *  UI never drifts from the persisted value) and surfaces in `error`. */
  async save(patch: Partial<UserSettings>): Promise<boolean> {
    this.saving = true;
    this.error = null;
    const previous = this.settings; // snapshot before the optimistic update
    this.settings = { ...this.settings, ...patch };
    this.apply();
    // Read-only demo (ADR-077): preferences apply for this visit only, so a
    // visitor can still try the theme and basemap without a refused write.
    if (auth.readOnly) {
      this.saving = false;
      return true;
    }
    try {
      this.settings = await saveMySettings(patch);
      this.apply();
      return true;
    } catch (e) {
      // Roll back the optimistic update + appearance so nothing the backend
      // rejected is left showing (and the localStorage cache stays truthful).
      this.settings = previous;
      this.apply();
      this.error = e instanceof Error ? e.message : String(e);
      if (e instanceof ApiError && e.status === 401) auth.signOut();
      return false;
    } finally {
      this.saving = false;
    }
  }

  /** Persist a saved filter-default snapshot + the auto-apply toggle together. */
  saveFilterDefault(snapshot: string, apply: boolean): Promise<boolean> {
    return this.save({ filter_default: snapshot, filter_default_apply: apply });
  }

  clearFilterDefault(): Promise<boolean> {
    return this.save({ filter_default: '', filter_default_apply: false });
  }

  /** Pin the given camera as my home view, switching to home mode. */
  setHomeView(v: MapView): Promise<boolean> {
    return this.save({ home_view: JSON.stringify(v), view_mode: 'home' });
  }

  clearHomeView(): Promise<boolean> {
    return this.save({ home_view: '', view_mode: 'last' });
  }

  /** Apply + cache the current effective appearance (data-theme + .cb class). */
  apply(): void {
    const a = this.appearance;
    applyAppearance(a);
    writeCachedAppearance(a);
  }

  private watchSystemTheme(): void {
    if (this.watching || typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }
    this.watching = true;
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      this.systemDark = e.matches;
      if (this.settings.theme === 'system') this.apply();
    });
  }
}

export const userSettings = new UserSettingsStore();
