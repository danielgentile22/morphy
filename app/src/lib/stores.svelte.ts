/**
 * Central app state — Svelte 5 runes.
 *
 * The app binds to the catalog, never to a hardcoded state. Boot reads
 * composite/index.json for the state list, then loads the active state's
 * catalog.json and its eager layer GeoJSON. Switching state re-runs the
 * same path. Nothing here knows that AR or MT specifically exist.
 */

import type { FeatureCollection } from 'geojson';
import type { Catalog, CompositeIndex, StateEntry } from './catalog';
import {
  compositeAssetUrl,
  countyBoundariesUrl,
  loadCatalog,
  loadFacets,
  loadGeoJson,
  loadIndex,
  parcelsAttrUrl,
  pmtilesUrl,
  resourceExists,
} from './data';
import { duckDb } from './duckdb';
import type { FacetData } from './facets';
import {
  FilterEngine,
  type FilterResult,
  type FilterStatus,
} from './filter-engine';
import { bboxCenter, parseGeomBbox } from './geo';
import { emptyFilters, isAnyFilterActive, type FilterState } from './filters';
import type { EntityKind, Props } from './schema';
import { readUrlState } from './url';

export type { FilterStatus } from './filter-engine';

/** Synthetic layer-visibility keys for the two base layers (not catalog
 *  entries — parcels come from PMTiles, the choropleth from an
 *  --app-assets GeoJSON). */
export const BASE_PARCELS = 'parcels';
export const BASE_COUNTY = 'county_boundaries';

/** A clicked / selected entity, shown in the detail panel. */
export interface Selection {
  kind: EntityKind;
  props: Props;
  /** Which loaded layer + feature index it came from — lets the map
   *  highlight the feature via feature-state. */
  featureRef?: { layer: string; index: number };
  /** lon/lat to recentre on, when known (e.g. a top-list row click). */
  at?: [number, number];
}

export type BootStatus = 'loading' | 'ready' | 'error';

/**
 * Views whose GeoJSON is large (5–19 MB each). Eager-loading every layer
 * is ~85 MB, so these load lazily — only when their toggle is switched on.
 */
export const HEAVY_VIEWS: ReadonlySet<string> = new Set([
  'parcels_hosting_infra',
  'distressed_parcels_hosting_infra',
  'llc_owned_parcels_with_infra',
  'towers_with_landowner',
]);

/** Layers / views shown by default when a state loads. */
const DEFAULT_ON: ReadonlySet<string> = new Set([
  'towers',
  'distress_overlays',
  'interestingness_top_1000',
]);

export interface LoadableAsset {
  name: string;
  geojsonPath: string;
}

/** Layers + views that carry GeoJSON and are small enough to boot-load. */
export function eagerAssets(catalog: Catalog): LoadableAsset[] {
  const out: LoadableAsset[] = [];
  for (const l of catalog.layers) {
    if (l.geojsonPath && !HEAVY_VIEWS.has(l.name)) {
      out.push({ name: l.name, geojsonPath: l.geojsonPath });
    }
  }
  for (const v of catalog.views) {
    if (v.geojsonPath && !HEAVY_VIEWS.has(v.name)) {
      out.push({ name: v.name, geojsonPath: v.geojsonPath });
    }
  }
  return out;
}

/** Initial visibility for every GeoJSON-bearing layer / view of a catalog. */
export function defaultVisibility(catalog: Catalog): Record<string, boolean> {
  const vis: Record<string, boolean> = {};
  for (const l of catalog.layers) {
    if (l.geojsonPath) vis[l.name] = DEFAULT_ON.has(l.name);
  }
  for (const v of catalog.views) {
    if (v.geojsonPath) vis[v.name] = DEFAULT_ON.has(v.name);
  }
  return vis;
}

/** Decide which state to open from the URL `?state=` param. */
export function pickInitialState(
  search: string,
  states: StateEntry[],
): { fips: string; invalidRequest: string | null } {
  const requested = new URLSearchParams(search).get('state');
  if (requested && states.some((s) => s.fips === requested)) {
    return { fips: requested, invalidRequest: null };
  }
  return {
    fips: states[0]?.fips ?? '',
    invalidRequest: requested && requested.trim() !== '' ? requested : null,
  };
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export class AppStore {
  status = $state<BootStatus>('loading');
  errorMessage = $state<string | null>(null);
  /** Non-fatal advisory (e.g. an unknown ?state= fell back to a real one). */
  notice = $state<string | null>(null);

  index = $state<CompositeIndex | null>(null);
  activeFips = $state<string | null>(null);
  catalog = $state<Catalog | null>(null);

  /** layer / view name -> loaded GeoJSON. */
  layerData = $state<Record<string, FeatureCollection>>({});
  /** County-choropleth GeoJSON for the active state (null if absent). */
  countyData = $state<FeatureCollection | null>(null);
  /** URL of the active state's parcels.pmtiles (null if not built). */
  parcelsUrl = $state<string | null>(null);
  /** Precomputed filter facets for the active state (null if absent). */
  facets = $state<FacetData | null>(null);
  /** True when the slim parquet exists — the DuckDB filter engine is usable. */
  filtersAvailable = $state(false);
  /** layer / view name -> visible on the map. */
  layerVisible = $state<Record<string, boolean>>({});
  /** layer / view names whose GeoJSON failed to load (toggle disabled). */
  failedLayers = $state<string[]>([]);

  /** The live parcel filter state. */
  filters = $state<FilterState>(emptyFilters());
  /** Count of parcels matching the active filter (null = no filter). */
  filterCount = $state<number | null>(null);
  /** Up to FILTER_FADE_CAP matching parcel ids — the map fades non-matches. */
  filterMatchIds = $state<string[]>([]);
  filterStatus = $state<FilterStatus>('idle');
  /** False until boot has read the deep-link — guards the URL-sync effect
   *  from erasing the query string before it is restored. */
  urlSyncReady = $state(false);

  selection = $state<Selection | null>(null);

  activeState = $derived<StateEntry | null>(
    this.index && this.activeFips
      ? (this.index.states.find((s) => s.fips === this.activeFips) ?? null)
      : null,
  );

  filtersActive = $derived(isAnyFilterActive(this.filters));

  /** Execution mechanics (debounce, token, cap, DuckDB calls) live in
   *  the engine; AppStore just mirrors the engine's result callback
   *  into the three reactive fields above. */
  #engine = new FilterEngine(
    {
      count: (where) => duckDb.count(where),
      matchingIds: (where, limit) => duckDb.matchingIds(where, limit),
      available: () => this.filtersAvailable,
    },
    (r: FilterResult) => {
      this.filterCount = r.count;
      this.filterMatchIds = r.matchIds;
      this.filterStatus = r.status;
    },
  );
  #selectionToken = 0;

  // ── synchronous mutations ────────────────────────────────────────────

  setSelection(sel: Selection | null): void {
    this.selection = sel;
    const token = ++this.#selectionToken;
    // A parcel clicked on the map / top-list carries only a partial set
    // of attributes (PMTiles baked tiles, or a view's GeoJSON). Fetch the
    // full row from DuckDB so the detail panel shows everything.
    if (sel?.kind === 'parcel' && this.filtersAvailable) {
      const parcelId = sel.props.parcel_id;
      if (typeof parcelId === 'string' && parcelId) {
        void this.#enrichParcel(parcelId, token);
      }
    }
  }
  clearSelection(): void {
    this.setSelection(null);
  }

  async #enrichParcel(parcelId: string, token: number): Promise<void> {
    const row = await duckDb.fetchParcel(parcelId).catch(() => null);
    if (!row || token !== this.#selectionToken) return;
    const sel = this.selection;
    if (sel?.kind !== 'parcel') return;
    this.selection = { ...sel, props: row };
  }

  /** Look a parcel up by exact APN; select + fly to it. Returns false if
   *  no parcel has that id. */
  async selectParcelByApn(parcelId: string): Promise<boolean> {
    const trimmed = parcelId.trim();
    if (!trimmed || !this.filtersAvailable) return false;
    const row = await duckDb.fetchParcel(trimmed).catch(() => null);
    if (!row) return false;
    this.#selectionToken += 1; // invalidate any in-flight enrich
    const bbox = parseGeomBbox(row.geom_bbox);
    this.selection = {
      kind: 'parcel',
      props: row,
      at: bbox ? bboxCenter(bbox) : undefined,
    };
    return true;
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

  // ── filters ──────────────────────────────────────────────────────────

  /** Merge a patch into the filter state and re-query (debounced). */
  updateFilter(patch: Partial<FilterState>): void {
    this.filters = { ...this.filters, ...patch };
    this.#engine.schedule(this.filters);
  }

  /** Clear every filter. */
  resetFilters(): void {
    this.filters = emptyFilters();
    this.#engine.schedule(this.filters);
  }

  /** Run the active filter immediately (bypassing the debounce). Kept
   *  as a public method for boot's deep-link restore and for callers
   *  that need a synchronous round-trip. */
  async applyFilters(): Promise<void> {
    await this.#engine.run(this.filters);
  }

  #resetFilterState(): void {
    this.filters = emptyFilters();
    this.#engine.reset();
  }

  // ── async boot / state switch ────────────────────────────────────────

  /**
   * @param initialSearch the URL query string captured *before* any
   * effect could rewrite it — boot reads the deep-link from here.
   */
  async boot(initialSearch: string): Promise<void> {
    this.status = 'loading';
    this.errorMessage = null;
    try {
      const index = await loadIndex();
      if (index.states.length === 0) {
        throw new Error(
          'composite/index.json lists no states. Run ' +
            '`python scripts/preprocess.py --app-assets` to generate it.',
        );
      }
      this.index = index;
      const pick = pickInitialState(initialSearch, index.states);
      if (pick.invalidRequest) {
        this.notice = `No composed state "${pick.invalidRequest}" — showing ${
          index.states.find((s) => s.fips === pick.fips)?.name ?? pick.fips
        } instead.`;
      }
      await this.selectState(pick.fips);
      this.#restoreFromUrl(initialSearch);
    } catch (e) {
      this.status = 'error';
      this.errorMessage = errMsg(e);
    } finally {
      // Boot is done — the URL-sync effect may now write the query string.
      this.urlSyncReady = true;
    }
  }

  /** Restore a deep-linked filter / selection from the URL after boot. */
  #restoreFromUrl(initialSearch: string): void {
    const url = readUrlState(initialSearch);
    if (url.filters && isAnyFilterActive(url.filters)) {
      this.filters = url.filters;
      void this.applyFilters();
    }
    if (url.selected) void this.selectParcelByApn(url.selected);
  }

  async selectState(fips: string): Promise<void> {
    this.status = 'loading';
    this.errorMessage = null;
    this.selection = null;
    this.#resetFilterState();
    try {
      const catalog = await loadCatalog(fips);
      const assets = eagerAssets(catalog);
      const [assetResults, countyData, hasParcelTiles, facets, hasAttrParquet] =
        await Promise.all([
          Promise.allSettled(
            assets.map((a) => loadGeoJson(compositeAssetUrl(fips, a.geojsonPath))),
          ),
          // Base layers + filter inputs — tolerant: a missing choropleth /
          // pmtiles / facets / slim parquet is not fatal.
          loadGeoJson(countyBoundariesUrl(fips)).catch(() => null),
          resourceExists(pmtilesUrl(fips)),
          loadFacets(fips).catch(() => null),
          resourceExists(parcelsAttrUrl(fips)),
        ]);
      const data: Record<string, FeatureCollection> = {};
      const failed: string[] = [];
      assetResults.forEach((r, i) => {
        if (r.status === 'fulfilled') data[assets[i].name] = r.value;
        else failed.push(assets[i].name);
      });

      this.activeFips = fips;
      this.catalog = catalog;
      this.layerData = data;
      this.failedLayers = failed;
      this.countyData = countyData;
      this.parcelsUrl = hasParcelTiles ? pmtilesUrl(fips) : null;
      this.facets = facets;
      this.filtersAvailable = hasAttrParquet;
      // Point the DuckDB filter engine at this state (lazy WASM init),
      // then fire a warm-up count so the user's first filter is instant
      // instead of paying the cold parquet-read cost.
      if (hasAttrParquet) {
        void duckDb.loadState(fips, parcelsAttrUrl(fips));
        void duckDb.count('').catch(() => undefined);
      }
      const visibility = defaultVisibility(catalog);
      visibility[BASE_PARCELS] = true;
      visibility[BASE_COUNTY] = true;
      this.layerVisible = visibility;
      this.status = 'ready';
      syncStateParam(fips);
    } catch (e) {
      this.status = 'error';
      this.errorMessage = errMsg(e);
    }
  }

  /** Lazy-load a heavy view's GeoJSON on first toggle-on. */
  async ensureLayerLoaded(name: string): Promise<void> {
    if (!this.catalog || !this.activeFips) return;
    if (this.layerData[name]) return;
    const view = this.catalog.views.find((v) => v.name === name);
    const geojsonPath = view?.geojsonPath;
    if (!geojsonPath) return;
    try {
      const fc = await loadGeoJson(compositeAssetUrl(this.activeFips, geojsonPath));
      this.layerData = { ...this.layerData, [name]: fc };
    } catch {
      this.failedLayers = [...this.failedLayers, name];
    }
  }
}

/** Reflect the active state in the URL so a reload reopens it. */
function syncStateParam(fips: string): void {
  if (typeof history === 'undefined') return;
  const url = new URL(location.href);
  url.searchParams.set('state', fips);
  history.replaceState(null, '', url);
}

export const app = new AppStore();
