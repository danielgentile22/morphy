/**
 * Central app state — Svelte 5 runes (UI overhaul #119: all-states map).
 *
 * The app boots the whole anchor set at once — there is no "active state". Boot
 * reads composite/index.json, then loads the national tower points, the
 * national solar points, the shared owners filter index (via the filter-model
 * store, mounted by the FilterPanel), and probes each anchor state's parcel
 * vector tiles. Filters narrow TOWERS only; parcels and solar are context
 * layers that render on zoom. The per-state catalog / slim-parquet / DuckDB
 * parcel-fade machinery was retired with the state selector.
 */

import type { FeatureCollection, Point } from 'geojson';
import type { CompositeIndex } from './catalog';
import { loadIndex, pmtilesUrl, probeResource } from './data';
import { loadNationalTowers, type TowerProps } from './towers';
import { loadSolarPoints, solarTotal, type SolarProps } from './solar';
import { errMsg, parcelSources as computeParcelSources, unionBounds } from './stores-helpers';
import type { ParcelSource } from './stores-helpers';
import type { EntityKind, Props } from './schema';
import { markTowersStart, markTowersDone } from './perf';

/** A pair of corners for MapLibre `fitBounds` — `[[w, s], [e, n]]`. */
export type BoundsCorners = [[number, number], [number, number]];

/** Synthetic layer-visibility key for the parcel base layer (it comes from
 *  PMTiles, not a catalog GeoJSON layer). */
export const BASE_PARCELS = 'parcels';

/** A clicked / selected entity, shown in the detail panel. */
export interface Selection {
  kind: EntityKind;
  props: Props;
  /** lon/lat to recentre on, when known (e.g. a top-list row click). */
  at?: [number, number];
}

export type BootStatus = 'loading' | 'ready' | 'error';
type Loadable = 'idle' | 'loading' | 'ready' | 'error';

export class AppStore {
  status = $state<BootStatus>('loading');
  errorMessage = $state<string | null>(null);
  /** Non-fatal advisory (e.g. no parcel tiles reachable). */
  notice = $state<string | null>(null);

  index = $state<CompositeIndex | null>(null);

  // ── structures-first map (Slice 4 / #50) ──────────────────────────────
  /** Tower points across every anchor state — the map's primary clustered
   *  layer. Loaded once so the all-anchors view survives section round-trips. */
  towerPoints = $state<FeatureCollection<Point, TowerProps> | null>(null);
  towersStatus = $state<Loadable>('idle');
  towersError = $state<string | null>(null);

  // ── national solar layer (#119) ───────────────────────────────────────
  /** Solar facilities across every anchor state — one persistent context
   *  layer, shown only when the Structure-type filter includes solar. */
  solarPoints = $state<FeatureCollection<Point, SolarProps> | null>(null);
  solarStatus = $state<Loadable>('idle');
  solarError = $state<string | null>(null);

  // ── parcels for all states (#119) ─────────────────────────────────────
  /** One parcel vector-tile source per anchor state whose tiles are present.
   *  The map adds them all; parcels draw on zoom anywhere across the anchors. */
  parcelSources = $state<ParcelSource[]>([]);

  /** Towers/parcels layer visibility (towers + parcels are always on now that
   *  the Layers panel is gone; solar visibility is derived from the filter). */
  layerVisible = $state<Record<string, boolean>>({});

  selection = $state<Selection | null>(null);

  /** A one-shot fly request — the FilterPanel's ASR search sets it to jump the
   *  map to a matched tower (Slice 6 / #52); MapView consumes it. */
  flyTarget = $state<{ center: [number, number]; zoom: number } | null>(null);

  /** Union of every anchor state's bbox — the all-anchors map framing.
   *  Null until the index has loaded. */
  anchorBounds = $derived<BoundsCorners | null>(unionBounds(this.index?.states ?? []));

  /** Static Solar tile total — sum of every anchor's solar-facility count.
   *  Fixed regardless of the active filter (solar can't be cluster-filtered). */
  solarCount = $derived<number>(solarTotal(this.index));

  // ── synchronous mutations ────────────────────────────────────────────

  setSelection(sel: Selection | null): void {
    this.selection = sel;
  }
  clearSelection(): void {
    this.selection = null;
  }

  /** Jump the map to a coordinate (FilterPanel ASR search). */
  flyTo(center: [number, number], zoom = 12): void {
    this.flyTarget = { center, zoom };
  }

  setLayerVisible(name: string, visible: boolean): void {
    this.layerVisible = { ...this.layerVisible, [name]: visible };
  }
  toggleLayer(name: string): void {
    this.setLayerVisible(name, !this.layerVisible[name]);
  }
  isLayerVisible(name: string): boolean {
    return this.layerVisible[name] === true;
  }
  dismissNotice(): void {
    this.notice = null;
  }

  // ── async boot ────────────────────────────────────────────────────────

  /** Idempotent: resolve once, shared by boot() + bootMap(). */
  private indexPromise: Promise<void> | null = null;
  /** Guards the heavy map-layer load so it runs at most once. */
  private mapBooted = false;

  /** Light boot — load only the composite index (needed for map framing + the
   *  static Solar tile). The heavy map stack (towers, parcel tiles, solar) is
   *  deferred to bootMap(), fired when the map is first shown, so a session that
   *  lands on the Dashboard never downloads/parses ~20 MB of map assets it
   *  doesn't render (PERF-001). */
  async boot(): Promise<void> {
    await this.ensureIndex();
  }

  private async ensureIndex(): Promise<void> {
    if (this.indexPromise) return this.indexPromise;
    this.status = 'loading';
    this.errorMessage = null;
    this.indexPromise = (async () => {
      try {
        const index = await loadIndex();
        if (index.states.length === 0) {
          throw new Error(
            'composite/index.json lists no states. Run ' +
              '`python scripts/preprocess.py --app-assets` to generate it.',
          );
        }
        this.index = index;
        // Towers + parcels are always on (the Layers panel was retired); solar
        // visibility is derived from the Structure-type filter in MapView.
        this.layerVisible = { towers: true, [BASE_PARCELS]: true };
        this.status = 'ready';
      } catch (e) {
        this.status = 'error';
        this.errorMessage = errMsg(e);
      }
    })();
    return this.indexPromise;
  }

  /** Heavy boot — the national tower layer + per-state parcel-tile probes,
   *  loaded the first time the map is shown (PERF-001). Solar stays lazy until
   *  its layer is enabled (PERF-014). Idempotent: runs at most once. */
  async bootMap(): Promise<void> {
    if (this.mapBooted) return;
    this.mapBooted = true;
    await this.ensureIndex();
    if (!this.index) return; // index failed → error screen already shown
    // National tower layer — independent of any one state; renders when ready.
    void this.loadTowers();
    // Probe each anchor state's parcel tiles → the per-state vector sources.
    const fipsList = this.index.states.map((s) => s.fips);
    const probeEntries = await Promise.all(
      fipsList.map(async (fips) => [fips, await probeResource(pmtilesUrl(fips))] as const),
    );
    this.parcelSources = computeParcelSources(this.index.states, Object.fromEntries(probeEntries));
    if (this.parcelSources.length === 0) {
      this.notice =
        'No parcel tiles are reachable — the map shows towers and solar only. ' +
        'Is the data server running?';
    }
  }

  /** Load tower points across every anchor state into one clustered source.
   *  Idempotent-ish: re-runnable on error; a success is kept for the session. */
  async loadTowers(): Promise<void> {
    if (this.towersStatus === 'loading' || this.towersStatus === 'ready') return;
    const fipsList = this.index?.states.map((s) => s.fips) ?? [];
    if (fipsList.length === 0) return;
    this.towersStatus = 'loading';
    this.towersError = null;
    // Bracket the tower critical path for the perf-probe (PRD #163 / #164):
    // probe + DuckDB init + union + marshal, ending when the FeatureCollection
    // is ready (first dots about to render). Passive — marks only.
    markTowersStart();
    try {
      this.towerPoints = await loadNationalTowers(fipsList);
      this.towersStatus = 'ready';
      markTowersDone(this.towerPoints.features.length);
    } catch (e) {
      this.towersError = errMsg(e);
      this.towersStatus = 'error';
    }
  }

  /** Load solar points across every anchor state into one national source.
   *  Mirrors `loadTowers`; a missing state's file degrades to fewer dots. */
  async loadSolar(): Promise<void> {
    if (this.solarStatus === 'loading' || this.solarStatus === 'ready') return;
    const fipsList = this.index?.states.map((s) => s.fips) ?? [];
    if (fipsList.length === 0) return;
    this.solarStatus = 'loading';
    this.solarError = null;
    try {
      this.solarPoints = await loadSolarPoints(fipsList);
      this.solarStatus = 'ready';
    } catch (e) {
      this.solarError = errMsg(e);
      this.solarStatus = 'error';
    }
  }
}

export const app = new AppStore();
