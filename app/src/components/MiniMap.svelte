<script lang="ts">
  import { onMount } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-csp-worker.js?url';
  import type { StyleSpecification } from 'maplibre-gl';
  import type { FeatureCollection, Point } from 'geojson';
  import type { Holding } from '../lib/leads-api';
  import { basemapStyle } from '../lib/basemap';

  // Same worker-URL guard as MapView (Vite 8 mis-compiles an inlined worker).
  maplibregl.setWorkerUrl(maplibreWorkerUrl);

  let { holdings }: { holdings: Holding[] } = $props();

  // Same keyless dark basemap as the main map's default.
  const BASEMAP: StyleSpecification = basemapStyle('dark');

  /** One footprint point per holding that has resolvable geometry. */
  function footprint(hs: Holding[]): FeatureCollection<Point> {
    return {
      type: 'FeatureCollection',
      features: hs
        .filter((h) => h.point != null)
        .map((h) => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: h.point as [number, number] },
          properties: { parcel_id: h.parcel_id, state: h.state },
        })),
    };
  }

  let container: HTMLDivElement;

  onMount(() => {
    const fc = footprint(holdings);
    // Nothing to plot (no geometry on any holding) — leave the placeholder.
    if (fc.features.length === 0) return;

    let map: maplibregl.Map | undefined;
    try {
      map = new maplibregl.Map({
        container,
        style: BASEMAP,
        center: fc.features[0].geometry.coordinates as [number, number],
        zoom: 5,
        attributionControl: { compact: true },
      });
    } catch (e) {
      console.warn('mini-map unavailable:', e);
      return;
    }

    const m = map;
    m.on('load', () => {
      m.addSource('footprint', { type: 'geojson', data: fc });
      m.addLayer({
        id: 'footprint-pts',
        type: 'circle',
        source: 'footprint',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 4, 10, 7],
          'circle-color': '#0072b2',
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ffffff',
        },
      });
      // Frame the whole footprint.
      if (fc.features.length > 1) {
        const b = new maplibregl.LngLatBounds();
        for (const f of fc.features) b.extend(f.geometry.coordinates as [number, number]);
        m.fitBounds(b, { padding: 36, maxZoom: 9, duration: 0 });
      }
      m.resize(); // the overlay container may have sized after construction
    });

    return () => m.remove();
  });
</script>

<div class="mini" bind:this={container} data-testid="lead-minimap"></div>

<style>
  .mini {
    width: 100%;
    height: 200px;
    border-radius: var(--radius);
    overflow: hidden;
    border: 1px solid var(--border);
    background: var(--panel-2);
  }
</style>
