<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import type {
    ExpressionSpecification,
    MapGeoJSONFeature,
    StyleSpecification,
  } from 'maplibre-gl';
  // MapLibre's prebuilt worker, imported as a static asset. Loading the
  // worker from a URL stops the bundler re-bundling MapLibre's worker
  // code — Vite 8 / Rolldown mis-compiles it (the GeoJSON tiler throws
  // "f is not defined"). Same pattern as the DuckDB-WASM worker.
  import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-csp-worker.js?url';
  import type { Point } from 'geojson';
  import type { FeatureCollection } from 'geojson';
  import { Protocol } from 'pmtiles';
  import { app } from '../lib/stores.svelte';
  import { layerColor, TOWER_MARKER_SVG, WONG } from '../lib/palette';
  import type { Props } from '../lib/schema';
  import { towerHoverHtml, filterTowers, type TowerProps } from '../lib/towers';
  import { showSolarLayer } from '../lib/solar';
  import { filterModel } from '../lib/filter-model.svelte';
  import { archivedAntennas } from '../lib/archived-antennas.svelte';
  import { towerHash } from '../lib/nav';
  import { userSettings } from '../lib/user-settings-store.svelte';
  import { basemapStyle, basemapTiles, resolveInitialView } from '../lib/basemap';
  import { readLastView, writeLastView } from '../lib/map-view-cache';

  maplibregl.setWorkerUrl(maplibreWorkerUrl);

  // Register the pmtiles:// protocol once so MapLibre can read the parcel
  // vector tiles via HTTP Range requests.
  maplibregl.addProtocol('pmtiles', new Protocol().tile);

  // Keyless raster basemap — the user's choice (Positron / Voyager / Dark
  // Matter), theme-aware (PRD #121). No API key, consistent with the no-backend
  // constraint. The live map hot-swaps only the basemap source's tiles when the
  // pref changes, so the app's tower/parcel/solar layers are never dropped.
  const initialStyle: StyleSpecification = basemapStyle(
    untrack(() => userSettings.basemap),
    untrack(() => userSettings.effectiveTheme),
  );

  const US_BOUNDS: [number, number, number, number] = [-125, 24, -66, 50];
  const TOWER_ICON = 'tower-marker';

  // Structures-first tower layer (Slice 4 / #50): one clustered source across
  // every anchor state, the map's primary clickable layer. Lives outside the
  // parcel/solar machinery (its own ids, never torn down) so the all-anchors
  // view persists across section changes (ADR-061 map persistence).
  const TOWERS_SRC = 'towers-all';
  const TL_CLUSTERS = 'towers-clusters';
  const TL_COUNT = 'towers-cluster-count';
  const TL_POINT = 'towers-point';
  const TOWER_LAYER_IDS = [TL_CLUSTERS, TL_COUNT, TL_POINT];
  let towerLayersAdded = false;
  let towerHandlersAttached = false;
  let towerPopup: maplibregl.Popup | undefined;

  // National solar layer (#119): one persistent context layer across all
  // anchors, shown only when the Structure-type filter includes solar.
  const SOLAR_SRC = 'solar-all';
  const SOLAR_LAYER = 'solar-point';
  let solarLayersAdded = false;

  // Parcel base layer — one PMTiles vector source PER anchor state (#119), so
  // parcels draw on zoom anywhere across AR/FL/MT/WV, not just a selected
  // state. Each source carries the same 'parcels' source-layer + baked
  // attributes; click + selection enumerate every state's fill layer.
  const parcelStatesAdded = new Set<string>();
  let parcelFillIds: string[] = [];
  /** The plain zoom fade, brightened for the selected parcel (the feature-state
   *  branch is the interpolation's output stop — `zoom` must stay the top-level
   *  interpolate input, so it can't wrap a `case`). Filtering never fades
   *  parcels (#119): they are stable context while the filter narrows towers. */
  const PARCELS_OPACITY: ExpressionSpecification = [
    'interpolate',
    ['linear'],
    ['zoom'],
    8,
    0,
    10,
    ['case', ['boolean', ['feature-state', 'selected'], false], 0.85, 0.55],
  ];

  function parcelSrcId(state: string): string {
    return `src:parcels:${state}`;
  }
  function parcelFillId(state: string): string {
    return `parcels:${state}:fill`;
  }
  function parcelLineId(state: string): string {
    return `parcels:${state}:line`;
  }

  let container: HTMLDivElement;
  let map: maplibregl.Map | undefined;
  let ready = $state(false);
  let towerIconReady = false;

  /** The parcel currently outlined via feature-state `selected` (and which
   *  state source it lives on, for the multi-source highlight). */
  let highlightedParcel: { source: string; id: string | number } | null = null;

  /** Interactive layer ids the pointer is currently over — drives the pointer
   *  cursor without a per-mousemove queryRenderedFeatures scan. */
  const hoveredLayers = new Set<string>();
  /** Teardown fns for the per-layer mouseenter/mouseleave listeners. */
  const hoverListenerCleanups: Array<() => void> = [];

  function rasterize(svg: string, px: number): Promise<ImageData> {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = px;
        canvas.height = px;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          reject(new Error('no 2d canvas context'));
          return;
        }
        ctx.drawImage(img, 0, 0, px, px);
        resolve(ctx.getImageData(0, 0, px, px));
      };
      img.onerror = () => reject(new Error('marker icon failed to decode'));
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    });
  }

  onMount(() => {
    const m = new maplibregl.Map({
      container,
      style: initialStyle,
      bounds: app.anchorBounds ?? US_BOUNDS,
      fitBoundsOptions: { padding: 28 },
      attributionControl: { compact: true },
    });
    map = m;

    // Persist the camera on every settle so "where I left off" can restore it
    // next session (PRD #121). Local/per-device — the pinned "home" view is the
    // backend-synced one.
    m.on('moveend', () => {
      const c = m.getCenter();
      writeLastView({ lng: c.lng, lat: c.lat, zoom: m.getZoom() });
    });
    // Test handle — lets E2E project feature coords to click the map
    // deterministically. Harmless in a local single-user app.
    (window as unknown as { __pilotMap?: maplibregl.Map }).__pilotMap = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    m.addControl(new maplibregl.ScaleControl({ unit: 'imperial' }), 'bottom-left');

    m.on('load', async () => {
      try {
        const data = await rasterize(TOWER_MARKER_SVG, 56);
        if (!m.hasImage(TOWER_ICON)) m.addImage(TOWER_ICON, data, { pixelRatio: 2 });
        towerIconReady = true;
      } catch (e) {
        // Non-fatal: towers fall back to circle markers.
        console.warn('tower icon unavailable, using circle markers:', e);
      }
      ready = true;
    });

    m.on('click', onMapClick);

    return () => {
      delete (window as unknown as { __pilotMap?: maplibregl.Map }).__pilotMap;
      towerPopup?.remove();
      towerPopup = undefined;
      towerLayersAdded = false;
      towerHandlersAttached = false;
      solarLayersAdded = false;
      parcelStatesAdded.clear();
      m.remove();
      map = undefined;
      ready = false;
    };
  });

  // Restore the startup camera once the per-user prefs resolve (PRD #121):
  // pinned home wins when set, else where I left off; otherwise the default
  // bounds (already fitted at construction) stand. One-shot, so it never fights
  // the user after they start panning.
  let initialViewApplied = false;
  $effect(() => {
    if (!map || initialViewApplied || !userSettings.loaded) return;
    initialViewApplied = true;
    const view = resolveInitialView(
      { viewMode: userSettings.settings.view_mode, home: userSettings.homeView },
      readLastView(),
    );
    if (view) map.jumpTo({ center: [view.lng, view.lat], zoom: view.zoom });
  });

  // Hot-swap just the basemap raster tiles when the basemap / theme pref
  // changes — leaves every app layer (towers, parcels, solar) untouched, unlike
  // a full setStyle.
  $effect(() => {
    const tiles = basemapTiles(userSettings.basemap, userSettings.effectiveTheme);
    const src = map?.getSource('basemap');
    if (src && 'setTiles' in src) {
      (src as maplibregl.RasterTileSource).setTiles(tiles);
    }
  });

  // ── hover cursor (shared by parcels) ─────────────────────────────────────

  function updateCursor(): void {
    if (map) map.getCanvas().style.cursor = hoveredLayers.size > 0 ? 'pointer' : '';
  }

  // Per-layer hover tracking for the pointer cursor. MapLibre hit-tests
  // internally for these delegated listeners, so the cursor costs nothing
  // per frame — unlike querying every interactive layer on each mousemove.
  function attachHover(layerId: string): void {
    if (!map) return;
    const enter = (): void => {
      hoveredLayers.add(layerId);
      updateCursor();
    };
    const leave = (): void => {
      hoveredLayers.delete(layerId);
      updateCursor();
    };
    map.on('mouseenter', layerId, enter);
    map.on('mouseleave', layerId, leave);
    hoverListenerCleanups.push(() => {
      map?.off('mouseenter', layerId, enter);
      map?.off('mouseleave', layerId, leave);
    });
  }

  /** MapLibre `match` expression: a distress-tier value → a fill colour. */
  function tierColorMatch(key: string): ExpressionSpecification {
    return [
      'match',
      ['get', key],
      'distressed',
      WONG.vermillion,
      'at-risk',
      WONG.orange,
      'transitional',
      WONG.yellow,
      'competitive',
      WONG.skyBlue,
      'attainment',
      WONG.bluishGreen,
      '#cdd2da',
    ] as ExpressionSpecification;
  }

  // ── parcels: one vector source per present anchor state (#119) ────────────

  function addParcelSources(): void {
    if (!map) return;
    // Keep parcels under the solar dots (and towers) regardless of which layer
    // loaded first — insert beneath solar when it already exists.
    const beforeId = map.getLayer(SOLAR_LAYER) ? SOLAR_LAYER : undefined;
    for (const { state, tilesUrl } of app.parcelSources) {
      if (parcelStatesAdded.has(state)) continue;
      const src = parcelSrcId(state);
      const absoluteUrl = new URL(tilesUrl, location.href).href;
      // promoteId lifts parcel_id to the feature id so a clicked parcel can be
      // outlined with setFeatureState.
      map.addSource(src, {
        type: 'vector',
        url: `pmtiles://${absoluteUrl}`,
        promoteId: { parcels: 'parcel_id' },
      });
      map.addLayer(
        {
          id: parcelFillId(state),
          type: 'fill',
          source: src,
          'source-layer': 'parcels',
          minzoom: 6,
          paint: {
            'fill-color': tierColorMatch('distress_tier'),
            'fill-opacity': PARCELS_OPACITY,
          },
        },
        beforeId,
      );
      map.addLayer(
        {
          id: parcelLineId(state),
          type: 'line',
          source: src,
          'source-layer': 'parcels',
          minzoom: 6,
          paint: {
          'line-color': [
            'case',
            ['boolean', ['feature-state', 'selected'], false],
            WONG.blue,
            '#5b6470',
          ],
          // A heavier outline emphasises parcels that host infrastructure (and
          // the selected parcel).
          'line-width': [
            'case',
            ['boolean', ['feature-state', 'selected'], false],
            2.4,
            [
              'any',
              ['coalesce', ['get', 'has_tower'], false],
              ['coalesce', ['get', 'has_solar'], false],
              ['coalesce', ['get', 'has_billboard'], false],
            ],
            1.8,
            0.25,
          ] as ExpressionSpecification,
          'line-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0, 11, 0.85],
          },
        },
        beforeId,
      );
      parcelStatesAdded.add(state);
      attachHover(parcelFillId(state));
    }
    parcelFillIds = [...parcelStatesAdded].map(parcelFillId);
    ensureTowersOnTop();
  }

  function clearParcelHighlight(): void {
    if (map && highlightedParcel) {
      map.removeFeatureState({ source: highlightedParcel.source, sourceLayer: 'parcels', id: highlightedParcel.id });
    }
    highlightedParcel = null;
  }

  // ── solar: one national context layer, gated on the structure-type filter ─

  function addSolarLayer(): void {
    if (!map || solarLayersAdded || !app.solarPoints) return;
    map.addSource(SOLAR_SRC, { type: 'geojson', data: app.solarPoints });
    map.addLayer({
      id: SOLAR_LAYER,
      type: 'circle',
      source: SOLAR_SRC,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 3, 12, 7],
        'circle-color': layerColor('solar_facilities'),
        'circle-stroke-width': 1,
        'circle-stroke-color': '#ffffff',
        'circle-opacity': 0.85,
      },
      layout: { visibility: showSolarLayer(filterModel.model) ? 'visible' : 'none' },
    });
    solarLayersAdded = true;
    ensureTowersOnTop();
  }

  function applySolarVisibility(): void {
    if (!map || !solarLayersAdded) return;
    map.setLayoutProperty(SOLAR_LAYER, 'visibility', showSolarLayer(filterModel.model) ? 'visible' : 'none');
  }

  // ── structures-first tower layer (ported verbatim from #50) ───────────────

  /** Open a clicked tower's detail page — a peek (#108, ADR-067). Every tower
   *  opens: a tower with no resolved landowner still gets a page (towerHash
   *  substitutes the NO_OWNER sentinel) so the user can fill in owner details. */
  function openTowerDetail(props: TowerProps): void {
    location.hash = towerHash(props.cid, props.asr);
  }

  // Click / hover handlers — attached once (the tower layers are never torn
  // down, so the layer-scoped listeners stay valid for the map's lifetime).
  function attachTowerHandlers(): void {
    if (!map || towerHandlersAttached) return;
    towerHandlersAttached = true;
    towerPopup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12 });

    map.on('mouseenter', TL_POINT, (e) => {
      if (!map) return;
      map.getCanvas().style.cursor = 'pointer';
      const f = e.features?.[0];
      if (!f) return;
      const coords = (f.geometry as Point).coordinates as [number, number];
      towerPopup?.setLngLat(coords).setHTML(towerHoverHtml(f.properties as TowerProps)).addTo(map);
    });
    map.on('mouseleave', TL_POINT, () => {
      if (map) map.getCanvas().style.cursor = '';
      towerPopup?.remove();
    });
    map.on('click', TL_POINT, (e) => {
      const f = e.features?.[0];
      if (f) openTowerDetail(f.properties as TowerProps);
    });

    map.on('mouseenter', TL_CLUSTERS, () => {
      if (map) map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', TL_CLUSTERS, () => {
      if (map) map.getCanvas().style.cursor = '';
    });
    map.on('click', TL_CLUSTERS, (e) => {
      if (!map) return;
      const f = map.queryRenderedFeatures(e.point, { layers: [TL_CLUSTERS] })[0];
      const clusterId = f?.properties?.cluster_id;
      const src = map.getSource(TOWERS_SRC) as maplibregl.GeoJSONSource | undefined;
      if (clusterId == null || !src) return;
      void src.getClusterExpansionZoom(clusterId).then((z) => {
        map?.easeTo({ center: (f.geometry as Point).coordinates as [number, number], zoom: z });
      });
    });
  }

  function addTowerLayers(data: FeatureCollection<Point, TowerProps>): void {
    if (!map || towerLayersAdded) return;
    map.addSource(TOWERS_SRC, {
      type: 'geojson',
      data,
      cluster: true,
      clusterRadius: 50,
      // Split into individual towers at high zoom (acceptance criterion).
      clusterMaxZoom: 11,
    });

    map.addLayer({
      id: TL_CLUSTERS,
      type: 'circle',
      source: TOWERS_SRC,
      filter: ['has', 'point_count'],
      paint: {
        'circle-color': WONG.blue,
        'circle-opacity': 0.85,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
        // Grow with the number of towers in the cluster.
        'circle-radius': ['step', ['get', 'point_count'], 13, 25, 17, 100, 22, 1000, 30],
      },
    });
    map.addLayer({
      id: TL_COUNT,
      type: 'symbol',
      source: TOWERS_SRC,
      filter: ['has', 'point_count'],
      layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12 },
      paint: { 'text-color': '#ffffff' },
    });

    if (towerIconReady) {
      map.addLayer({
        id: TL_POINT,
        type: 'symbol',
        source: TOWERS_SRC,
        filter: ['!', ['has', 'point_count']],
        layout: {
          'icon-image': TOWER_ICON,
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          'icon-size': ['interpolate', ['linear'], ['zoom'], 6, 0.4, 11, 0.6, 14, 0.85],
        },
        // Dim inactive towers so live structures stand out.
        paint: { 'icon-opacity': ['case', ['get', 'active'], 0.95, 0.45] },
      });
    } else {
      map.addLayer({
        id: TL_POINT,
        type: 'circle',
        source: TOWERS_SRC,
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 6, 4, 14, 8],
          'circle-color': ['case', ['get', 'active'], WONG.black, '#9aa0aa'],
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ffffff',
        },
      });
    }
    towerLayersAdded = true;
    attachTowerHandlers();
  }

  /** Add (first time) or refresh the tower source data, keep it on top, and
   *  honour the `towers` visibility toggle. */
  function syncTowerLayers(): void {
    if (!map || !app.towerPoints) return;
    // The shared FilterModel narrows the tower layer to matching owners
    // (null = no filter active → every tower). Same model as the candidates
    // list, so the two surfaces stay consistent (Slice 6 / #52). Archived
    // antennas drop out too unless "show archived" is on (UI overhaul round 2).
    const data = filterTowers(
      app.towerPoints,
      filterModel.matchingClusterIds,
      archivedAntennas.filter,
    );
    if (!towerLayersAdded) {
      addTowerLayers(data);
    } else {
      const src = map.getSource(TOWERS_SRC) as maplibregl.GeoJSONSource | undefined;
      src?.setData(data);
    }
    ensureTowersOnTop();
    applyTowerVisibility();
  }

  /** Keep the tower layers above the parcel + solar context layers. */
  function ensureTowersOnTop(): void {
    if (!map || !towerLayersAdded) return;
    for (const id of TOWER_LAYER_IDS) {
      if (map.getLayer(id)) map.moveLayer(id);
    }
  }

  /** Tower layers follow the `towers` visibility flag (default on). */
  function applyTowerVisibility(): void {
    if (!map || !towerLayersAdded) return;
    const vis = app.isLayerVisible('towers') ? 'visible' : 'none';
    for (const id of TOWER_LAYER_IDS) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis);
    }
  }

  // ── interaction ──────────────────────────────────────────────────────────

  function onMapClick(e: maplibregl.MapMouseEvent): void {
    if (!map) return;
    // Towers are the primary layer: a tower/cluster hit is handled by its own
    // layer listener (open detail / expand cluster), so don't also select the
    // parcel beneath it.
    if (towerLayersAdded && app.isLayerVisible('towers')) {
      const towerIds = TOWER_LAYER_IDS.filter((id) => map!.getLayer(id));
      if (towerIds.length && map.queryRenderedFeatures(e.point, { layers: towerIds }).length) {
        return;
      }
    }
    // Otherwise the parcel base layer (visible once zoomed in) — query every
    // present anchor state's fill layer.
    const fillIds = parcelFillIds.filter((id) => map!.getLayer(id));
    const feature = fillIds.length
      ? map.queryRenderedFeatures(e.point, { layers: fillIds })[0]
      : undefined;
    if (!feature) {
      app.clearSelection();
      return;
    }
    selectParcel(feature);
  }

  /** Select a clicked parcel (baked PMTiles tile properties only — the
   *  per-state DuckDB enrichment was retired with the state selector) and
   *  outline it via feature-state on whichever state source it belongs to. */
  function selectParcel(f: MapGeoJSONFeature): void {
    const props = (f.properties ?? {}) as Props;
    app.setSelection({ kind: 'parcel', props });
    clearParcelHighlight();
    if (f.id != null) {
      map!.setFeatureState({ source: f.source, sourceLayer: 'parcels', id: f.id }, { selected: true });
      highlightedParcel = { source: f.source, id: f.id };
    }
  }

  // ── effects ──────────────────────────────────────────────────────────────

  // Add the per-state parcel sources once they've been probed. Idempotent —
  // addParcelSources skips states already added — so this only adds new ones.
  $effect(() => {
    void app.parcelSources;
    if (!map || !ready) return;
    untrack(() => addParcelSources());
  });

  // Build the national solar layer once its data loads; keep its visibility in
  // step with the Structure-type filter (the single control for solar now).
  $effect(() => {
    void app.solarPoints;
    void filterModel.model;
    if (!map || !ready) return;
    untrack(() => {
      addSolarLayer();
      applySolarVisibility();
    });
  });

  // Build / refresh the all-anchors tower layer once its data loads. Kept on
  // its own effect so a filter change re-narrows it without rebuilding parcels.
  $effect(() => {
    void app.towerPoints;
    void filterModel.matchingClusterIds; // re-narrow towers on a filter change
    void archivedAntennas.asrs; // re-narrow when an antenna is (un)archived
    void archivedAntennas.show; // …or when "show archived" is toggled
    if (!map || !ready) return;
    untrack(() => syncTowerLayers());
  });

  // Toggle the tower layer visibility from the store.
  $effect(() => {
    void app.layerVisible;
    if (!map || !ready) return;
    untrack(() => applyTowerVisibility());
  });

  // One-shot fly to a tower matched by the FilterPanel ASR search.
  $effect(() => {
    const t = app.flyTarget;
    if (!map || !ready || !t) return;
    map.flyTo({ center: t.center, zoom: t.zoom, duration: 700 });
  });

  // Frame the map on all anchors (structures-first — survey the whole pilot at
  // once). There is no per-state framing anymore; the union of anchor bboxes is
  // the only framing.
  $effect(() => {
    const anchors = app.anchorBounds;
    if (!map || !anchors) return;
    map.fitBounds(anchors, { padding: 28, duration: ready ? 700 : 0 });
  });

  // Clear the parcel outline when the selection is cleared (Escape / panel
  // close). A new parcel selection sets its own highlight imperatively.
  $effect(() => {
    const sel = app.selection;
    if (!map || !ready) return;
    if (!sel) untrack(() => clearParcelHighlight());
  });
</script>

<div class="map" bind:this={container} data-testid="map"></div>

<style>
  .map {
    position: absolute;
    inset: 0;
  }
  /* MapLibre canvas focus outline is distracting for a kiosk-style app. */
  .map :global(.maplibregl-canvas:focus) {
    outline: none;
  }
</style>
