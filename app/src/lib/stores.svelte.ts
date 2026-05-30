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
  probeResource,
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
import { loadTowerPoints, type TowerProps } from './towers';
import type { Point } from 'geojson';

/** A pair of corners for MapLibre `fitBounds` — `[[w, s], [e, n]]`. */
export type BoundsCorners = [[number, number], [number, number]];

/** Where the map is framed: all anchors at once (structures-first default),
 *  or zoomed to one focused state (an explicit StateSelector / deep-link pick). */
export type MapFocus = { kind: 'anchors' } | { kind: 'state'; fips: string };

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

export {
  HEAVY_VIEWS,
  eagerAssets,
  defaultVisibility,
  pickInitialState,
  type LoadableAsset,
} from './stores-helpers';
import {
  defaultVisibility,
  eagerAssets,
  errMsg,
  pickInitialState,
  syncStateParam,
  unionBounds,
} from './stores-helpers';

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
  /** Bumped once per *settled* engine result (idle/error — never the
   *  intermediate querying emit) so the map fade coalesces to a single
   *  clear+reapply per query instead of one per filterMatchIds change. */
  filterResultEpoch = $state(0);
  /** False until boot has read the deep-link — guards the URL-sync effect
   *  from erasing the query string before it is restored. */
  urlSyncReady = $state(false);

  selection = $state<Selection | null>(null);
  /** Status of the async full-row enrichment for a selected parcel — the
   *  detail panel shows a hint while loading and a banner on failure. */
  enrichmentStatus = $state<'idle' | 'loading' | 'error'>('idle');

  // ── structures-first map (Slice 4 / #50) ──────────────────────────────
  /** Tower points across every anchor state — the map's primary clustered
   *  layer. Loaded once (independent of the active state) so the all-anchors
   *  view survives state switches and route round-trips. */
  towerPoints = $state<FeatureCollection<Point, TowerProps> | null>(null);
  towersStatus = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
  towersError = $state<string | null>(null);
  /** How the map is framed (all anchors by default; a state on explicit pick). */
  mapFocus = $state<MapFocus>({ kind: 'anchors' });

  activeState = $derived<StateEntry | null>(
    this.index && this.activeFips
      ? (this.index.states.find((s) => s.fips === this.activeFips) ?? null)
      : null,
  );

  /** Union of every anchor state's bbox — the all-anchors map framing.
   *  Null until the index has loaded. */
  anchorBounds = $derived<BoundsCorners | null>(unionBounds(this.index?.states ?? []));

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
      // A settled result drives the map's filter-fade exactly once; the
      // transient querying emit (empty ids) must not clear the live fade.
      if (r.status !== 'querying') this.filterResultEpoch++;
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
    const parcelId = sel?.kind === 'parcel' ? sel.props.parcel_id : null;
    if (sel?.kind === 'parcel' && this.filtersAvailable && typeof parcelId === 'string' && parcelId) {
      this.enrichmentStatus = 'loading';
      void this.#enrichParcel(parcelId, token);
    } else {
      this.enrichmentStatus = 'idle';
    }
  }
  clearSelection(): void {
    this.setSelection(null);
  }

  async #enrichParcel(parcelId: string, token: number): Promise<void> {
    const row = await duckDb.fetchParcel(parcelId).catch(() => null);
    if (token !== this.#selectionToken) return; // superseded by a newer selection
    if (!row) {
      this.enrichmentStatus = 'error';
      return;
    }
    const sel = this.selection;
    if (sel?.kind !== 'parcel') return;
    this.selection = { ...sel, props: row };
    this.enrichmentStatus = 'idle';
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
    this.enrichmentStatus = 'idle'; // row is already the full record
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
      // Tower points span all anchors and are independent of the active
      // state — kick the load off now and let the map render them when ready.
      void this.loadTowers();
      const pick = pickInitialState(initialSearch, index.states);
      if (pick.invalidRequest) {
        this.notice = `No composed state "${pick.invalidRequest}" — showing ${
          index.states.find((s) => s.fips === pick.fips)?.name ?? pick.fips
        } instead.`;
      }
      // Structures-first default: always frame all anchors at once. (?state=
      // still picks which state's parcels/catalog load, and is auto-written to
      // the URL — so it can't be read as an explicit "focus this state"
      // intent; that comes only from a StateSelector pick → focusState.)
      this.mapFocus = { kind: 'anchors' };
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
    this.enrichmentStatus = 'idle';
    this.#resetFilterState();
    try {
      const catalog = await loadCatalog(fips);
      const assets = eagerAssets(catalog);
      const [assetResults, countyData, parcelTilesProbe, facets, attrParquetProbe] =
        await Promise.all([
          Promise.allSettled(
            assets.map((a) => loadGeoJson(compositeAssetUrl(fips, a.geojsonPath))),
          ),
          // Base layers + filter inputs — tolerant: a missing choropleth /
          // pmtiles / facets / slim parquet is not fatal.
          loadGeoJson(countyBoundariesUrl(fips)).catch(() => null),
          probeResource(pmtilesUrl(fips)),
          loadFacets(fips).catch(() => null),
          probeResource(parcelsAttrUrl(fips)),
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
      this.parcelsUrl = parcelTilesProbe === 'present' ? pmtilesUrl(fips) : null;
      this.facets = facets;
      this.filtersAvailable = attrParquetProbe === 'present';
      // A genuine 404 (absent parquet) degrades silently; an unreachable
      // probe means the server is down — say so rather than pretend the
      // filter data simply doesn't exist for this state.
      if (attrParquetProbe === 'unreachable') {
        this.notice =
          'Could not reach the parcel attribute data — filters and parcel search are ' +
          'unavailable. Is the data server running?';
      }
      // Point the DuckDB filter engine at this state (lazy WASM init),
      // then fire a warm-up count so the user's first filter is instant
      // instead of paying the cold parquet-read cost.
      if (this.filtersAvailable) {
        void duckDb.loadState(fips, parcelsAttrUrl(fips)).catch(() => {
          // Registration failed after a successful HEAD — disable filters
          // and tell the user instead of leaving a silently broken panel.
          this.filtersAvailable = false;
          this.notice = 'Filters are unavailable — the parcel attribute data failed to load.';
        });
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

  /** Load tower points across every anchor state into one clustered source.
   *  Idempotent-ish: re-runnable on error; a success is kept for the session. */
  async loadTowers(): Promise<void> {
    if (this.towersStatus === 'loading' || this.towersStatus === 'ready') return;
    const fipsList = this.index?.states.map((s) => s.fips) ?? [];
    if (fipsList.length === 0) return;
    this.towersStatus = 'loading';
    this.towersError = null;
    try {
      this.towerPoints = await loadTowerPoints(fipsList);
      this.towersStatus = 'ready';
    } catch (e) {
      this.towersError = errMsg(e);
      this.towersStatus = 'error';
    }
  }

  /** Frame the map on one state and load its detail (parcels / catalog).
   *  The StateSelector calls this; boot uses the lower-level selectState so
   *  it can keep the all-anchors framing. */
  async focusState(fips: string): Promise<void> {
    this.mapFocus = { kind: 'state', fips };
    await this.selectState(fips);
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

export const app = new AppStore();
