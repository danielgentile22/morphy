// Runes store for tunable scoring (UI overhaul P4 / #114). Holds the active
// scoring config + derives a cid→score map over the in-memory owners index,
// recomputed instantly on every weight change. Explore's tower list + the
// owner page rank by `scoreOf`. #115 swaps the config for a named preset.

import { filterModel } from './filter-model.svelte';
import { request, ApiError } from './leads-api';
import { auth } from './auth-store.svelte';
import {
  effectiveScore,
  defaultConfig,
  shouldApplyTeamDefault,
  type ScoringConfig,
  type ScoreExtents,
  type ScoreWeights,
} from './scoring';

/** A tenant-shared named scoring preset (#115). */
export interface ScoringPreset {
  id: number;
  name: string;
  config: ScoringConfig;
  is_default: boolean;
}

function handle(e: unknown): void {
  if (e instanceof ApiError && e.status === 401) auth.signOut();
}

class ScoringStore {
  config = $state<ScoringConfig>(defaultConfig());
  presets = $state<ScoringPreset[]>([]);
  activePresetId = $state<number | null>(null);
  presetError = $state<string | null>(null);

  /** Normalization extents — the shared single extents pass (filterModel), with
   *  the scorer's height floor of 1 (a zero normalizer would divide the height
   *  feature away). */
  extents = $derived.by<ScoreExtents>(() => {
    const e = filterModel.ownerExtents;
    return {
      assessedMax: e.assessedMax,
      portfolioMax: e.portfolioMax,
      towerMax: e.towerMax,
      heightMax: Math.max(1, e.heightMax),
      carrierMax: e.carrierMax,
    };
  });

  /** cid → score under the active config (baked when default, else computed). */
  scoreById = $derived.by(() => {
    const m = new Map<string, number>();
    const config = this.config;
    const ext = this.extents;
    for (const o of filterModel.owners) {
      m.set(o.display_cluster_id, effectiveScore(o, config, ext));
    }
    return m;
  });

  scoreOf(cid: string): number | null {
    return this.scoreById.get(cid) ?? null;
  }

  get useDefault(): boolean {
    return this.config.useDefault;
  }
  get weights(): ScoreWeights {
    return this.config.weights;
  }

  setWeight(key: keyof ScoreWeights, value: number): void {
    // Touching a weight switches off the baked default into custom mode + off
    // any active preset (it's now an unsaved custom config).
    this.config = { useDefault: false, weights: { ...this.config.weights, [key]: value } };
    this.activePresetId = null;
  }

  /** Apply several weight changes in one config update — one scoreById rebuild
   *  instead of one per key, used by the debounced slider commit (PERF-003). */
  setWeights(partial: Partial<ScoreWeights>): void {
    this.config = { useDefault: false, weights: { ...this.config.weights, ...partial } };
    this.activePresetId = null;
  }

  // ── named presets (#115, tenant-shared) ──────────────────────────────────
  async loadPresets(): Promise<void> {
    try {
      const res = await request<{ presets: ScoringPreset[] }>('/scoring-presets');
      this.presets = res.presets;
      // Apply the team default once on load (if nothing is active yet).
      const def = shouldApplyTeamDefault(this.presets, this.activePresetId, this.config);
      if (def) this.apply(def);
    } catch (e) {
      handle(e);
    }
  }

  apply(preset: ScoringPreset): void {
    this.setConfig(preset.config);
    this.activePresetId = preset.id;
  }

  /** Save the current config as a named, tenant-shared preset. */
  async save(name: string, makeDefault = false): Promise<boolean> {
    this.presetError = null;
    try {
      const p = await request<ScoringPreset>('/scoring-presets', {
        method: 'POST',
        body: JSON.stringify({ name, config: this.config, is_default: makeDefault }),
      });
      this.presets = [...this.presets, p].sort((a, b) => a.name.localeCompare(b.name));
      this.activePresetId = p.id;
      return true;
    } catch (e) {
      handle(e);
      this.presetError = e instanceof Error ? e.message : String(e);
      return false;
    }
  }

  async setDefault(id: number): Promise<void> {
    try {
      await request<ScoringPreset>(`/scoring-presets/${id}/default`, { method: 'POST' });
      this.presets = this.presets.map((p) => ({ ...p, is_default: p.id === id }));
    } catch (e) {
      handle(e);
    }
  }

  async remove(id: number): Promise<void> {
    try {
      await request<void>(`/scoring-presets/${id}`, { method: 'DELETE' });
      this.presets = this.presets.filter((p) => p.id !== id);
      if (this.activePresetId === id) this.reset();
    } catch (e) {
      handle(e);
    }
  }

  /** Adopt a full config (e.g. when a named preset is loaded — #115). */
  setConfig(config: ScoringConfig): void {
    this.config = { useDefault: config.useDefault, weights: { ...config.weights } };
  }

  reset(): void {
    this.config = defaultConfig();
    this.activePresetId = null;
  }
}

export const scoring = new ScoringStore();
