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
  import type { FeatureCollection, Point } from 'geojson';
  import { Protocol } from 'pmtiles';
  import { app, BASE_COUNTY, BASE_PARCELS } from '../lib/stores.svelte';
  import { entityKind } from '../lib/catalog';
  import { detectGeometryClasses } from '../lib/geo';
  import { layerColor, TOWER_MARKER_SVG, WONG } from '../lib/palette';
  import type { Props } from '../lib/schema';
  import { towerHoverHtml, resolveTowerLeadKey, type TowerProps } from '../lib/towers';

  maplibregl.setWorkerUrl(maplibreWorkerUrl);

  // Register the pmtiles:// protocol once so MapLibre can read the parcel
  // vector tiles via HTTP Range requests.
  maplibregl.addProtocol('pmtiles', new Protocol().tile);

  // Keyless raster basemap — Carto Positron. No API key, consistent with
  // the no-backend constraint.
  const BASEMAP_STYLE: StyleSpecification = {
    version: 8,
    sources: {
      basemap: {
        type: 'raster',
        tiles: [
          'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
          'https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
          'https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
        ],
        tileSize: 256,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
          'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      },
    },
    layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }],
  };

  const US_BOUNDS: [number, number, number, number] = [-125, 24, -66, 50];
  const TOWER_ICON = 'tower-marker';

  // Structures-first tower layer (Slice 4 / #50): one clustered source across
  // every anchor state, the map's primary clickable layer. Lives outside the
  // per-state catalog machinery (its own ids, never torn down on a state
  // switch) so the all-anchors view persists. `towers` is the catalog name the
  // LayerPanel toggle drives.
  const TOWERS_SRC = 'towers-all';
  const TL_CLUSTERS = 'towers-clusters';
  const TL_COUNT = 'towers-cluster-count';
  const TL_POINT = 'towers-point';
  const TOWER_LAYER_IDS = [TL_CLUSTERS, TL_COUNT, TL_POINT];
  let towerLayersAdded = false;
  let towerHandlersAttached = false;
  let towerPopup: maplibregl.Popup | undefined;

  // parcels:fill opacity — the plain zoom fade, and the filtered form
  // where DuckDB-matched parcels (feature-state `match`) stay bright.
  const PARCELS_OPACITY_NORMAL: ExpressionSpecification = [
    'interpolate',
    ['linear'],
    ['zoom'],
    8,
    0,
    10,
    0.55,
  ];
  // `zoom` must be the top-level interpolate input — it cannot be nested
  // inside a `case` — so the feature-state branch is the interpolation's
  // output stop instead.
  const PARCELS_OPACITY_FILTERED: ExpressionSpecification = [
    'interpolate',
    ['linear'],
    ['zoom'],
    8,
    0,
    10,
    ['case', ['boolean', ['feature-state', 'match'], false], 0.8, 0.05],
  ];

  let container: HTMLDivElement;
  let map: maplibregl.Map | undefined;
  let ready = $state(false);
  let towerIconReady = false;

  /** MapLibre layer id -> logical catalog layer/view name. */
  const layerIdToName = new Map<string, string>();
  /** Logical name -> the MapLibre layer ids rendering it. */
  const nameToLayerIds = new Map<string, string[]>();
  /** Source ids currently added. */
  const sourceIds = new Set<string>();
  let interactiveLayerIds: string[] = [];
  let highlighted: { source: string; id: number } | null = null;
  /** The fips whose layers are currently rendered. A change means a state
   *  switch (full rebuild); an unchanged fips with new layerData keys means
   *  a lazy view loaded (incremental add — no full re-tile). */
  let syncedFips: string | null = null;
  /** Interactive layer ids the pointer is currently over — drives the
   *  pointer cursor without a per-mousemove queryRenderedFeatures scan. */
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
      style: BASEMAP_STYLE,
      bounds: app.activeState?.bbox ?? US_BOUNDS,
      fitBoundsOptions: { padding: 28 },
      attributionControl: { compact: true },
    });
    map = m;
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
      m.remove();
      map = undefined;
      ready = false;
    };
  });

  // ── layer sync ─────────────────────────────────────────────────────────

  function clearRenderedLayers(): void {
    if (!map) return;
    for (const id of layerIdToName.keys()) {
      if (map.getLayer(id)) map.removeLayer(id);
    }
    for (const id of sourceIds) {
      if (map.getSource(id)) map.removeSource(id);
    }
    layerIdToName.clear();
    nameToLayerIds.clear();
    sourceIds.clear();
    interactiveLayerIds = [];
    detachHover();
    highlighted = null;
  }

  function fillColor(name: string): ExpressionSpecification | string {
    if (name === 'distress_overlays') {
      return [
        'match',
        ['get', 'overlay_type'],
        'opportunity_zone',
        WONG.blue,
        'qct',
        WONG.skyBlue,
        '#9aa0aa',
      ] as ExpressionSpecification;
    }
    return layerColor(name);
  }

  function fillOpacity(name: string): number {
    if (name === 'interestingness_top_1000') return 0.55;
    if (name === 'distress_overlays') return 0.22;
    return 0.4;
  }

  function selectedWidth(base: number): ExpressionSpecification {
    return [
      'case',
      ['boolean', ['feature-state', 'selected'], false],
      base + 2.5,
      base,
    ] as ExpressionSpecification;
  }

  function register(layerId: string, name: string, interactive: boolean): void {
    layerIdToName.set(layerId, name);
    const ids = nameToLayerIds.get(name) ?? [];
    ids.push(layerId);
    nameToLayerIds.set(name, ids);
    if (interactive) {
      interactiveLayerIds.push(layerId);
      attachHover(layerId);
    }
  }

  function updateCursor(): void {
    if (map) map.getCanvas().style.cursor = hoveredLayers.size > 0 ? 'pointer' : '';
  }

  // Per-layer hover tracking for the pointer cursor. MapLibre hit-tests
  // internally for these delegated listeners, so the cursor costs nothing
  // per frame — unlike querying every interactive layer on each mousemove
  // (10-30×/s over 50k+ features). Hidden layers don't fire mouseenter, so
  // no visibility filter is needed (applyVisibility prunes stale entries
  // when a layer the pointer sits over is toggled off).
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

  function detachHover(): void {
    for (const off of hoverListenerCleanups) off();
    hoverListenerCleanups.length = 0;
    hoveredLayers.clear();
    updateCursor();
  }

  // `beforeId`, when given, inserts the sublayers beneath that layer so an
  // incrementally-added polygon view stays under the point markers (the
  // full-sync two-pass order). Omitted during a full sync (append).
  function addPolygonSublayers(name: string, beforeId?: string): void {
    if (!map) return;
    const src = `src:${name}`;
    const fillId = `${name}:fill`;
    const lineId = `${name}:line`;
    map.addLayer(
      {
        id: fillId,
        type: 'fill',
        source: src,
        filter: ['match', ['geometry-type'], ['Polygon', 'MultiPolygon'], true, false],
        paint: { 'fill-color': fillColor(name), 'fill-opacity': fillOpacity(name) },
      },
      beforeId,
    );
    map.addLayer(
      {
        id: lineId,
        type: 'line',
        source: src,
        filter: ['match', ['geometry-type'], ['Polygon', 'MultiPolygon'], true, false],
        paint: { 'line-color': fillColor(name), 'line-width': selectedWidth(1.1) },
      },
      beforeId,
    );
    register(fillId, name, true);
    register(lineId, name, false);
  }

  function addPointSublayer(name: string): void {
    if (!map) return;
    const src = `src:${name}`;
    if (name === 'towers' && towerIconReady) {
      const symId = `${name}:symbol`;
      map.addLayer({
        id: symId,
        type: 'symbol',
        source: src,
        filter: ['match', ['geometry-type'], ['Point', 'MultiPoint'], true, false],
        layout: {
          'icon-image': TOWER_ICON,
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          // Small at state zoom — there can be ~16k towers and full-size
          // icons blanket the map — growing to a legible icon when zoomed in.
          'icon-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            5,
            0.22,
            8,
            0.4,
            11,
            0.62,
            14,
            0.9,
          ],
        },
        paint: { 'icon-opacity': 0.9 },
      });
      register(symId, name, true);
      return;
    }
    const circleId = `${name}:circle`;
    map.addLayer({
      id: circleId,
      type: 'circle',
      source: src,
      filter: ['match', ['geometry-type'], ['Point', 'MultiPoint'], true, false],
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 3, 12, 7],
        'circle-color': layerColor(name),
        'circle-stroke-width': selectedWidth(1),
        'circle-stroke-color': '#ffffff',
      },
    });
    register(circleId, name, true);
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

  // County choropleth — shaded by ARC tier, fades out as parcels fade in.
  function addChoropleth(): void {
    if (!map || !app.countyData) return;
    const src = `src:${BASE_COUNTY}`;
    map.addSource(src, { type: 'geojson', data: app.countyData, generateId: true });
    sourceIds.add(src);
    map.addLayer({
      id: `${BASE_COUNTY}:fill`,
      type: 'fill',
      source: src,
      paint: {
        'fill-color': tierColorMatch('tier'),
        'fill-opacity': ['interpolate', ['linear'], ['zoom'], 7, 0.6, 10, 0],
      },
    });
    map.addLayer({
      id: `${BASE_COUNTY}:line`,
      type: 'line',
      source: src,
      paint: {
        'line-color': '#ffffff',
        'line-width': selectedWidth(1),
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0.85, 10, 0],
      },
    });
    register(`${BASE_COUNTY}:fill`, BASE_COUNTY, true);
    register(`${BASE_COUNTY}:line`, BASE_COUNTY, false);
  }

  // Parcel base layer — PMTiles vector tiles, discovered by convention.
  function addParcels(): void {
    if (!map || !app.parcelsUrl) return;
    const src = `src:${BASE_PARCELS}`;
    const absoluteUrl = new URL(app.parcelsUrl, location.href).href;
    // promoteId lifts parcel_id to the feature id so the filter pipeline
    // can highlight matches with setFeatureState.
    map.addSource(src, {
      type: 'vector',
      url: `pmtiles://${absoluteUrl}`,
      promoteId: { parcels: 'parcel_id' },
    });
    sourceIds.add(src);
    map.addLayer({
      id: `${BASE_PARCELS}:fill`,
      type: 'fill',
      source: src,
      'source-layer': 'parcels',
      minzoom: 6,
      paint: {
        'fill-color': tierColorMatch('distress_tier'),
        'fill-opacity': PARCELS_OPACITY_NORMAL,
      },
    });
    map.addLayer({
      id: `${BASE_PARCELS}:line`,
      type: 'line',
      source: src,
      'source-layer': 'parcels',
      minzoom: 6,
      paint: {
        'line-color': '#5b6470',
        // A heavier outline emphasises parcels that host infrastructure.
        'line-width': [
          'case',
          [
            'any',
            ['coalesce', ['get', 'has_tower'], false],
            ['coalesce', ['get', 'has_solar'], false],
            ['coalesce', ['get', 'has_billboard'], false],
          ],
          1.8,
          0.25,
        ],
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0, 11, 0.85],
      },
    });
    register(`${BASE_PARCELS}:fill`, BASE_PARCELS, true);
    register(`${BASE_PARCELS}:line`, BASE_PARCELS, false);
  }

  // ── structures-first tower layer ─────────────────────────────────────────

  /** Navigate a clicked tower to its landowner's Lead, or warn when its
   *  owner can't be clustered into a Lead (blank parcel_owner). */
  function openTowerLead(props: TowerProps): void {
    const key = resolveTowerLeadKey(props);
    if (!key) {
      app.notice = 'No landowner on file for this tower — nothing to open.';
      return;
    }
    location.hash = `#/lead/${encodeURIComponent(key)}`;
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
      if (f) openTowerLead(f.properties as TowerProps);
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

  function addTowerLayers(): void {
    if (!map || towerLayersAdded || !app.towerPoints) return;
    map.addSource(TOWERS_SRC, {
      type: 'geojson',
      data: app.towerPoints,
      cluster: true,
      clusterRadius: 50,
      // Split into individual towers at high zoom (acceptance criterion).
      clusterMaxZoom: 11,
    });
    // NB: deliberately NOT added to `sourceIds` — the tower source/layers are
    // managed independently and must survive `clearRenderedLayers()` on a
    // state switch (they only go away on full map teardown).

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
    if (!towerLayersAdded) {
      addTowerLayers();
    } else {
      const src = map.getSource(TOWERS_SRC) as maplibregl.GeoJSONSource | undefined;
      src?.setData(app.towerPoints);
    }
    ensureTowersOnTop();
    applyTowerVisibility();
  }

  /** Keep the tower layers above the per-state catalog/parcel layers, which a
   *  state-switch rebuild re-adds on top. */
  function ensureTowersOnTop(): void {
    if (!map || !towerLayersAdded) return;
    for (const id of TOWER_LAYER_IDS) {
      if (map.getLayer(id)) map.moveLayer(id);
    }
  }

  /** Tower layers follow the catalog `towers` visibility toggle (default on). */
  function applyTowerVisibility(): void {
    if (!map || !towerLayersAdded) return;
    const vis = app.isLayerVisible('towers') ? 'visible' : 'none';
    for (const id of TOWER_LAYER_IDS) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis);
    }
  }

  function syncLayers(data: Record<string, FeatureCollection>): void {
    if (!map) return;
    clearRenderedLayers();

    // Base layers first — drawn underneath the catalog overlays.
    addChoropleth();
    addParcels();

    // Detect each layer's geometry families once. A layer can mix families
    // (e.g. solar_facilities has Point + Polygon), so this can't be read
    // from catalog.geometry_type — but it need only be scanned a single
    // time, not once per sublayer pass.
    const entries = Object.entries(data).map(([name, fc]) => ({
      name,
      fc,
      classes: detectGeometryClasses(fc.features),
    }));
    for (const { name, fc } of entries) {
      const src = `src:${name}`;
      map.addSource(src, { type: 'geojson', data: fc, generateId: true });
      sourceIds.add(src);
    }
    // Polygon sublayers (drawn under points).
    for (const { name, classes } of entries) {
      if (classes.hasPolygon) addPolygonSublayers(name);
    }
    // Point / symbol sublayers (drawn on top). `towers` is map-owned (the
    // global clustered layer) and never arrives in catalog data here, but
    // skip it defensively so a future per-state load can't double-render it.
    for (const { name, classes } of entries) {
      if (name !== 'towers' && classes.hasPoint) addPointSublayer(name);
    }
    applyVisibility();
    reapplyHighlight();
    applyFilterFade();
    // Catalog/parcel layers were just (re)added on top — restore the tower
    // layers to the very top so they stay the primary clickable layer.
    ensureTowersOnTop();
  }

  /** The lowest point/symbol layer id, so an incrementally-added polygon
   *  view can be inserted beneath the markers (matching the full-sync
   *  two-pass order). */
  function firstPointLayerId(): string | undefined {
    for (const id of layerIdToName.keys()) {
      if (id.endsWith(':circle') || id.endsWith(':symbol')) return id;
    }
    return undefined;
  }

  // Add a single catalog GeoJSON layer (source + sublayers) without
  // tearing down the rest of the map — used when a lazy view loads. A full
  // clearRenderedLayers()/syncLayers() would re-tile every source and
  // flicker the selection; this touches only the new layer.
  function addCatalogLayer(name: string, fc: FeatureCollection): void {
    if (!map || name === 'towers' || map.getSource(`src:${name}`)) return;
    const src = `src:${name}`;
    map.addSource(src, { type: 'geojson', data: fc, generateId: true });
    sourceIds.add(src);
    const classes = detectGeometryClasses(fc.features);
    if (classes.hasPolygon) addPolygonSublayers(name, firstPointLayerId());
    if (classes.hasPoint) addPointSublayer(name);
  }

  // Re-apply the selected feature's highlight after a re-sync recreated
  // its source (e.g. a lazy view loaded), so the outline does not flicker off.
  function reapplyHighlight(): void {
    if (!map) return;
    const sel = app.selection;
    if (!sel?.featureRef) return;
    const ref = { source: `src:${sel.featureRef.layer}`, id: sel.featureRef.index };
    if (map.getSource(ref.source)) {
      map.setFeatureState(ref, { selected: true });
      highlighted = ref;
    }
  }

  // Fade non-matching parcels when a filter is active. The matching ids
  // (up to FILTER_FADE_CAP) are written as feature-state in batches so a
  // large result set never blocks the frame.
  let matchGeneration = 0;
  function applyFilterFade(): void {
    const fillId = `${BASE_PARCELS}:fill`;
    if (!map || !map.getLayer(fillId)) return;
    const active = app.filtersActive;
    map.setPaintProperty(
      fillId,
      'fill-opacity',
      active ? PARCELS_OPACITY_FILTERED : PARCELS_OPACITY_NORMAL,
    );

    const generation = ++matchGeneration;
    const src = `src:${BASE_PARCELS}`;
    if (map.getSource(src)) map.removeFeatureState({ source: src, sourceLayer: 'parcels' });
    if (!active) return;

    const ids = app.filterMatchIds;
    let i = 0;
    const step = (): void => {
      if (!map || generation !== matchGeneration) return;
      const end = Math.min(i + 6000, ids.length);
      for (; i < end; i++) {
        map.setFeatureState({ source: src, sourceLayer: 'parcels', id: ids[i] }, { match: true });
      }
      if (i < ids.length) requestAnimationFrame(step);
    };
    step();
  }

  function applyVisibility(): void {
    if (!map) return;
    for (const [name, ids] of nameToLayerIds) {
      const visible = app.isLayerVisible(name);
      for (const id of ids) {
        if (map.getLayer(id)) {
          map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
        }
        // A layer toggled off under a stationary pointer never fires
        // mouseleave — drop it so the cursor doesn't stick on 'pointer'.
        if (!visible) hoveredLayers.delete(id);
      }
    }
    updateCursor();
  }

  // ── interaction ──────────────────────────────────────────────────────────

  /** Interactive layer ids that exist on the map and whose layer is visible. */
  function visibleInteractive(): string[] {
    return interactiveLayerIds.filter((id) => {
      if (!map?.getLayer(id)) return false;
      const name = layerIdToName.get(id);
      return name ? app.isLayerVisible(name) : false;
    });
  }

  function onMapClick(e: maplibregl.MapMouseEvent): void {
    if (!map) return;
    // Towers are the primary layer: a tower/cluster hit is handled by its own
    // layer listener (open Lead / expand cluster), so don't also select the
    // parcel beneath it.
    if (towerLayersAdded && app.isLayerVisible('towers')) {
      const towerIds = TOWER_LAYER_IDS.filter((id) => map!.getLayer(id));
      if (towerIds.length && map.queryRenderedFeatures(e.point, { layers: towerIds }).length) {
        return;
      }
    }
    const interactive = visibleInteractive();
    const baseFills = [`${BASE_PARCELS}:fill`, `${BASE_COUNTY}:fill`];

    // Catalog overlays (markers, view polygons) win — they are the
    // specific things a user aims at.
    const overlayIds = interactive.filter((id) => !baseFills.includes(id));
    let feature: MapGeoJSONFeature | undefined = overlayIds.length
      ? map.queryRenderedFeatures(e.point, { layers: overlayIds })[0]
      : undefined;

    // Otherwise the base layer — parcels when zoomed in, county when not.
    if (!feature) {
      const baseId = map.getZoom() >= 10 ? `${BASE_PARCELS}:fill` : `${BASE_COUNTY}:fill`;
      if (interactive.includes(baseId)) {
        feature = map.queryRenderedFeatures(e.point, { layers: [baseId] })[0];
      }
    }
    if (!feature) {
      app.clearSelection();
      return;
    }
    selectFromFeature(feature);
  }

  function selectFromFeature(f: MapGeoJSONFeature): void {
    const name = layerIdToName.get(f.layer.id);
    if (!name) return;
    const props = (f.properties ?? {}) as Props;

    // Parcels come from PMTiles — scalar baked attributes only.
    if (name === BASE_PARCELS) {
      app.setSelection({ kind: 'parcel', props });
      return;
    }
    const index = typeof f.id === 'number' ? f.id : -1;
    if (name === BASE_COUNTY) {
      const original = index >= 0 ? app.countyData?.features[index] : undefined;
      app.setSelection({
        kind: 'county',
        props: (original?.properties as Props | undefined) ?? props,
        featureRef: index >= 0 ? { layer: BASE_COUNTY, index } : undefined,
      });
      return;
    }
    // A catalog GeoJSON layer / view — resolve the original feature so
    // nested-object properties survive (queryRenderedFeatures stringifies them).
    if (!app.catalog) return;
    const kind = entityKind(app.catalog, name);
    if (!kind) return;
    // Only reference the source feature when its GeoJSON is actually
    // loaded; a featureRef into a failed / unloaded layer can't be
    // resolved or highlighted. The stringified queryRenderedFeatures
    // props still give the detail panel something to show.
    const dataReady = !!app.layerData[name] && !app.failedLayers.includes(name);
    const original = dataReady && index >= 0 ? app.layerData[name]?.features[index] : undefined;
    app.setSelection({
      kind,
      props: (original?.properties as Props | undefined) ?? props,
      featureRef: dataReady && index >= 0 ? { layer: name, index } : undefined,
    });
  }

  // ── effects ──────────────────────────────────────────────────────────────

  // Keep rendered layers in step with the store. A state switch (activeFips
  // change) rebuilds everything; growing layerData within the same state
  // (a lazy view loaded) adds only the new layers. The imperative body is
  // untracked so this effect depends solely on the data/state identity —
  // not on layerVisible / selection / filter state, which have their own
  // effects (otherwise a visibility toggle or filter change would trigger
  // a full rebuild here).
  $effect(() => {
    const data = app.layerData;
    const fips = app.activeFips;
    void app.countyData;
    void app.parcelsUrl;
    if (!map || !ready) return;
    untrack(() => {
      if (fips !== syncedFips) {
        syncedFips = fips;
        syncLayers(data);
        return;
      }
      let added = false;
      for (const [name, fc] of Object.entries(data)) {
        if (!map!.getSource(`src:${name}`)) {
          addCatalogLayer(name, fc);
          added = true;
        }
      }
      if (added) {
        applyVisibility();
        reapplyHighlight();
        ensureTowersOnTop();
      }
    });
  });

  // Toggle MapLibre layer visibility from the store.
  $effect(() => {
    void app.layerVisible;
    if (!map || !ready) return;
    applyVisibility();
    applyTowerVisibility();
  });

  // Build / refresh the all-anchors tower layer once its data loads. Kept on
  // its own effect (not the per-state catalog sync) so a state switch never
  // rebuilds it — the structures-first layer is global.
  $effect(() => {
    void app.towerPoints;
    if (!map || !ready) return;
    untrack(() => syncTowerLayers());
  });

  // Fade non-matching parcels once per *settled* filter result. Driven by
  // the engine's result epoch (bumped only on non-querying emits), so a
  // rapid slider drag yields one clear+reapply per query — not per tick,
  // and never the transient empty querying state. applyFilterFade's reads
  // of filtersActive/filterMatchIds are untracked so they don't re-add the
  // per-change triggering we're coalescing away.
  $effect(() => {
    void app.filterResultEpoch;
    if (!map || !ready) return;
    untrack(() => applyFilterFade());
  });

  // Frame the map. Default is all anchors (structures-first — survey the
  // whole pilot at once); an explicit state pick / deep-link frames that one.
  $effect(() => {
    const focus = app.mapFocus;
    const anchors = app.anchorBounds;
    if (!map) return;
    let bounds: maplibregl.LngLatBoundsLike | undefined;
    if (focus.kind === 'state') {
      bounds = app.index?.states.find((s) => s.fips === focus.fips)?.bbox;
    } else {
      bounds = anchors ?? undefined;
    }
    if (!bounds) return;
    map.fitBounds(bounds, { padding: 28, duration: ready ? 700 : 0 });
  });

  // Highlight the selected feature; fly to it when a centre is supplied.
  $effect(() => {
    const sel = app.selection;
    if (!map || !ready) return;
    if (highlighted && map.getSource(highlighted.source)) {
      map.removeFeatureState(highlighted);
    }
    highlighted = null;
    if (sel?.featureRef) {
      const ref = { source: `src:${sel.featureRef.layer}`, id: sel.featureRef.index };
      if (map.getSource(ref.source)) {
        map.setFeatureState(ref, { selected: true });
        highlighted = ref;
      }
    }
    if (sel?.at) {
      map.flyTo({
        center: sel.at,
        zoom: Math.max(map.getZoom(), 11),
        duration: 700,
      });
    }
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
