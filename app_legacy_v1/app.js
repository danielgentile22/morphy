/* Graham County cell-tower / parcel prototype. Vanilla Leaflet, no build step. */
(function () {
  "use strict";

  // ── Bounding box & defaults ──────────────────────────────────────────────
  const GRAHAM_BBOX = [[35.10, -83.98], [35.51, -83.55]]; // [[S,W],[N,E]]
  const TOWER_CLUSTER_RADIUS_M = 400; // upscale marker if multiple within this many meters

  // ── State ────────────────────────────────────────────────────────────────
  const state = {
    towers: null,           // GeoJSON FeatureCollection (FCC ASR ≥200 ft)
    uls: null,              // GeoJSON FeatureCollection (FCC ULS cellular)
    hifld: null,            // GeoJSON FeatureCollection (HIFLD cellular)
    parcels: null,
    oz: null,
    parcelById: new Map(),  // apn → feature
    layers: {
      oz: null,
      parcels: null,
      towers: null,
      uls: null,
      hifld: null,
    },
    parcelLayerById: new Map(), // apn → leaflet layer
    visibility: { oz: true, parcels: true, towers: true, uls: true, hifld: false },
    filters: { onlyHost: false, onlyOz: false, owner: "", carrier: "" },
    selected: null,         // { kind: 'tower'|'parcel'|'uls'|'hifld', id }
  };

  // ── Map setup ────────────────────────────────────────────────────────────
  const map = L.map("map", {
    zoomControl: true,
    preferCanvas: true, // canvas-rendered parcels are MUCH faster for 9k polygons
  });
  map.fitBounds(GRAHAM_BBOX);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(map);

  // ── Sidebar collapse ─────────────────────────────────────────────────────
  const sidebarEl = document.getElementById("sidebar");
  document.getElementById("toggle-sidebar").addEventListener("click", () => {
    sidebarEl.classList.remove("open");
    setTimeout(() => map.invalidateSize(), 200);
  });
  document.getElementById("open-sidebar").addEventListener("click", () => {
    sidebarEl.classList.add("open");
    setTimeout(() => map.invalidateSize(), 200);
  });

  // ── Layer styles (Wong CB-safe palette) ──────────────────────────────────
  const ozStyle = {
    color: "#0072B2",          // sky-blue stroke
    weight: 1,
    fillColor: "#56B4E9",      // sky-blue fill
    fillOpacity: 0.22,
  };

  function parcelStyle(feat) {
    const p = feat.properties;
    if (p.has_tower && p.in_oz) {
      // Magenta/purple — distinct hue family from the yellow host fill.
      return { color: "#6b3a59", weight: 1.6, fillColor: "#CC79A7", fillOpacity: 0.75 };
    }
    if (p.has_tower) {
      return { color: "#6b5d00", weight: 1.6, fillColor: "#F0E442", fillOpacity: 0.75 };
    }
    return { color: "#5b6470", weight: 0.6, opacity: 0.55, fillColor: "#ffffff", fillOpacity: 0 };
  }

  function parcelHoverStyle(feat) {
    const base = parcelStyle(feat);
    return Object.assign({}, base, { color: "#000000", weight: 2, opacity: 1, fillOpacity: Math.max(base.fillOpacity, 0.18) });
  }

  function parcelSelectedStyle(feat) {
    const base = parcelStyle(feat);
    // Heavy black border for selection (works for all CB types).
    return Object.assign({}, base, { color: "#000000", weight: 3, opacity: 1, fillOpacity: Math.max(base.fillOpacity, 0.32) });
  }

  // ── Tower marker (red circle w/ inline tower SVG) ────────────────────────
  const TOWER_SVG = `
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none"
         stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M5 21 L12 5 L19 21" />
      <path d="M8 14 H16" />
      <path d="M9.5 10.5 H14.5" />
      <circle cx="12" cy="3.5" r="1.2" fill="#ffffff" stroke="none"/>
    </svg>`;

  function makeTowerIcon(size) {
    const s = size || 18;
    return L.divIcon({
      className: "", // we style via .tower-marker; avoid leaflet defaults
      html: `<div class="tower-marker${s > 22 ? " cluster" : ""}"
               style="width:${s}px;height:${s}px;margin-left:${-s/2}px;margin-top:${-s/2}px;">
                ${TOWER_SVG}
             </div>`,
      iconSize: [s, s],
      iconAnchor: [s / 2, s / 2],
    });
  }

  // Stable per-feature jitter so co-located markers in a collection don't overlap fully.
  function jitterFor(features, f, radius) {
    const groups = new Map();
    features.forEach((u) => {
      const key = `${u.geometry.coordinates[0].toFixed(4)},${u.geometry.coordinates[1].toFixed(4)}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(u);
    });
    const key = `${f.geometry.coordinates[0].toFixed(4)},${f.geometry.coordinates[1].toFixed(4)}`;
    const grp = groups.get(key) || [f];
    const i = grp.indexOf(f);
    if (grp.length === 1) return [0, 0];
    const angle = (i / grp.length) * 2 * Math.PI;
    return [Math.sin(angle) * radius, Math.cos(angle) * radius];
  }

  // ── Cluster sizing: count nearby towers ──────────────────────────────────
  function metersBetween(a, b) {
    return map.distance([a[0], a[1]], [b[0], b[1]]);
  }
  function towerSizes(features) {
    const pts = features.map((f) => f.geometry.coordinates); // [lon,lat]
    return features.map((_, i) => {
      let near = 0;
      for (let j = 0; j < pts.length; j++) {
        if (i === j) continue;
        const d = metersBetween([pts[i][1], pts[i][0]], [pts[j][1], pts[j][0]]);
        if (d < TOWER_CLUSTER_RADIUS_M) near++;
      }
      return near > 0 ? 26 : 18;
    });
  }

  // ── Data loading ─────────────────────────────────────────────────────────
  async function loadJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
    return await res.json();
  }

  // ── v3 catalog-driven loader ─────────────────────────────────────────────
  // Layout: data/processed/composite/<state_fips>/{towers,parcels,...}.geojson
  // Tries the v3 path first; falls back to the v1 hardcoded paths.

  function getStateParam() {
    const qs = new URLSearchParams(window.location.search);
    return qs.get("state");   // null = first available
  }

  async function discoverStates() {
    // Probe a known set of state FIPS in parallel for catalog.json.
    // (The composite/ directory is filesystem-only; no directory listing
    // over plain HTTP — so we just probe and keep what answers 200.)
    const candidates = [
      "01","02","04","05","06","08","09","10","11","12","13","15","16","17",
      "18","19","20","21","22","23","24","25","26","27","28","29","30","31",
      "32","33","34","35","36","37","38","39","40","41","42","44","45","46",
      "47","48","49","50","51","53","54","55","56",
    ];
    const out = [];
    const probes = candidates.map(async (f) => {
      try {
        const cat = await loadJson(`../data/processed/composite/${f}/catalog.json`);
        out.push(cat);
      } catch { /* skip */ }
    });
    await Promise.all(probes);
    out.sort((a, b) => (a.state_name || "").localeCompare(b.state_name || ""));
    return out;
  }

  function aliasParcelFields(features) {
    // v3 canonical schema uses parcel_id / parcel_id_full. v1 app code uses
    // apn / apn_full. Alias for backwards compatibility without rewriting
    // every accessor. Likewise owner_name stays the same.
    features.forEach((f) => {
      const p = f.properties;
      if (p.parcel_id && !p.apn) p.apn = p.parcel_id;
      if (p.parcel_id_full && !p.apn_full) p.apn_full = p.parcel_id_full;
    });
  }

  async function loadAll() {
    const empty = { type: "FeatureCollection", features: [] };

    // Try v3 composite path first.
    const requestedState = getStateParam();
    const states = await discoverStates();
    let useV3 = states.length > 0;
    let activeCatalog = null;

    if (useV3) {
      activeCatalog = requestedState
        ? states.find((s) => s.state_fips === requestedState) || states[0]
        : states[0];
      buildStateSelector(states, activeCatalog.state_fips);
    } else {
      console.warn("No v3 composite/ outputs found — falling back to v1 paths.");
    }

    const basePath = useV3
      ? `../data/processed/composite/${activeCatalog.state_fips}`
      : "../data/processed";

    const towersPath = useV3 && activeCatalog.layers && activeCatalog.layers.towers
      ? `${basePath}/${activeCatalog.layers.towers.geojson_path}`
      : `${basePath}/towers.geojson`;
    const parcelsPath = useV3 && activeCatalog.layers && activeCatalog.layers.parcels
      ? `${basePath}/${activeCatalog.layers.parcels.simplified_geojson_path || activeCatalog.layers.parcels.geojson_path}`
      : `${basePath}/parcels.geojson`;
    const ozPath = useV3 && activeCatalog.layers && activeCatalog.layers.distress_overlays
      ? `${basePath}/${activeCatalog.layers.distress_overlays.geojson_path}`
      : `${basePath}/opportunity_zones.geojson`;

    const ulsPromise = loadJson(`${basePath}/uls_cellular.geojson`).catch(() => empty);
    const hifldPromise = loadJson(`${basePath}/hifld_towers.geojson`).catch(() => empty);

    const [towers, parcels, oz, uls, hifld] = await Promise.all([
      loadJson(towersPath).catch(() => empty),
      loadJson(parcelsPath).catch(() => empty),
      loadJson(ozPath).catch(() => empty),
      ulsPromise,
      hifldPromise,
    ]);
    state.towers = towers;
    state.parcels = parcels;
    state.oz = oz;
    state.uls = uls;
    state.hifld = hifld;

    aliasParcelFields(state.parcels.features);

    state.parcels.features.forEach((f) => {
      const k = f.properties.apn || f.properties.apn_full;
      if (k) state.parcelById.set(k, f);
    });

    if (useV3 && activeCatalog) {
      buildViewToggles(activeCatalog);
      // Re-fit map to the active state's bbox if available.
      try {
        const bounds = parcelLikeBounds(state.parcels) || parcelLikeBounds(state.towers);
        if (bounds) map.fitBounds(bounds);
      } catch {}
    }

    buildOwnerFilter();
    buildLayers();
    refreshSummary();
  }

  function parcelLikeBounds(fc) {
    if (!fc || !fc.features || fc.features.length === 0) return null;
    try {
      const layer = L.geoJSON(fc);
      return layer.getBounds();
    } catch { return null; }
  }

  function buildStateSelector(states, activeFips) {
    // Find or create the state selector in the sidebar.
    let host = document.getElementById("state-selector-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "state-selector-host";
      host.style.padding = "8px 12px";
      host.style.borderBottom = "1px solid #ddd";
      const sb = document.getElementById("sidebar");
      if (sb && sb.firstChild) sb.insertBefore(host, sb.firstChild);
    }
    host.innerHTML = "";
    const lbl = document.createElement("label");
    lbl.textContent = "State: ";
    lbl.style.fontWeight = "bold";
    host.appendChild(lbl);
    const sel = document.createElement("select");
    sel.style.marginLeft = "8px";
    states.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.state_fips;
      opt.textContent = `${s.state_abbr} — ${s.state_name}`;
      if (s.state_fips === activeFips) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", () => {
      const qs = new URLSearchParams(window.location.search);
      qs.set("state", sel.value);
      window.location.search = qs.toString();
    });
    host.appendChild(sel);
  }

  function buildViewToggles(catalog) {
    // Render one checkbox per view defined in the catalog. Loads/unloads
    // the view's GeoJSON as a separate Leaflet layer.
    if (!catalog.views) return;
    let host = document.getElementById("view-toggles-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "view-toggles-host";
      host.style.padding = "8px 12px";
      host.style.borderBottom = "1px solid #ddd";
      const sb = document.getElementById("sidebar");
      if (sb && sb.firstChild) sb.insertBefore(host, sb.firstChild);
    }
    host.innerHTML = "<h3 style='margin:4px 0 6px'>Views</h3>";
    Object.entries(catalog.views).forEach(([viewName, viewMeta]) => {
      if (!viewMeta.geojson_path) return;  // only views that wrote GeoJSON
      const row = document.createElement("label");
      row.style.display = "block";
      row.style.fontSize = "12px";
      row.title = viewMeta.description || viewName;
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.viewName = viewName;
      cb.dataset.path = `../data/processed/composite/${catalog.state_fips}/${viewMeta.geojson_path}`;
      cb.addEventListener("change", async () => {
        if (cb.checked) {
          try {
            const fc = await loadJson(cb.dataset.path);
            const layer = L.geoJSON(fc, {
              pointToLayer: (feat, latlng) =>
                L.circleMarker(latlng, { radius: 8, color: "#d62728", weight: 2, fillOpacity: 0.6 }),
              style: { color: "#d62728", weight: 2, fillOpacity: 0.3 },
            });
            layer.addTo(map);
            cb._layer = layer;
          } catch (e) { console.error(`view ${viewName} load failed:`, e); }
        } else if (cb._layer) {
          map.removeLayer(cb._layer);
          cb._layer = null;
        }
      });
      row.appendChild(cb);
      row.appendChild(document.createTextNode(" " + viewName.replace(/_/g, " ")));
      row.appendChild(document.createTextNode(` (${viewMeta.rows || 0})`));
      host.appendChild(row);
    });
  }

  // ── Build layers ─────────────────────────────────────────────────────────
  function buildLayers() {
    state.layers.oz = L.geoJSON(state.oz, {
      style: ozStyle,
      onEachFeature: (f, layer) => {
        layer.on("click", () => {
          showOzDetails(f);
        });
      },
    });

    state.layers.parcels = L.geoJSON(state.parcels, {
      style: parcelStyle,
      onEachFeature: (f, layer) => {
        const key = f.properties.apn || f.properties.apn_full;
        if (key) state.parcelLayerById.set(key, layer);
        layer.on({
          mouseover: () => {
            if (state.selected && state.selected.kind === "parcel" && state.selected.id === key) return;
            layer.setStyle(parcelHoverStyle(f));
          },
          mouseout: () => {
            if (state.selected && state.selected.kind === "parcel" && state.selected.id === key) {
              layer.setStyle(parcelSelectedStyle(f));
            } else {
              layer.setStyle(parcelStyle(f));
            }
          },
          click: (ev) => {
            L.DomEvent.stopPropagation(ev);
            showParcelDetails(f, layer);
          },
        });
      },
    });

    // ULS sites — small hollow blue rings.
    state.layers.uls = L.geoJSON(state.uls, {
      pointToLayer: (f, latlng) => {
        const j = jitterFor(state.uls.features, f, 0.00012);
        const ll = L.latLng(latlng.lat + j[0], latlng.lng + j[1]);
        const icon = L.divIcon({
          className: "",
          html: '<div class="uls-marker" style="margin-left:-7px;margin-top:-7px;"></div>',
          iconSize: [12, 12],
          iconAnchor: [6, 6],
        });
        return L.marker(ll, { icon });
      },
      onEachFeature: (f, layer) => {
        layer.on("click", (ev) => {
          L.DomEvent.stopPropagation(ev);
          showUlsDetails(f);
        });
      },
    });

    // HIFLD sites — small yellow diamonds. Off by default (overlaps ULS).
    state.layers.hifld = L.geoJSON(state.hifld, {
      pointToLayer: (f, latlng) => {
        const j = jitterFor(state.hifld.features, f, 0.00020);
        const ll = L.latLng(latlng.lat + j[0], latlng.lng + j[1]);
        const icon = L.divIcon({
          className: "",
          html: '<div class="hifld-marker" style="margin-left:-7px;margin-top:-7px;"></div>',
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        });
        return L.marker(ll, { icon });
      },
      onEachFeature: (f, layer) => {
        layer.on("click", (ev) => {
          L.DomEvent.stopPropagation(ev);
          showHifldDetails(f);
        });
      },
    });

    const sizes = towerSizes(state.towers.features);
    state.layers.towers = L.geoJSON(state.towers, {
      pointToLayer: (f, latlng) => {
        const idx = state.towers.features.indexOf(f);
        return L.marker(latlng, { icon: makeTowerIcon(sizes[idx]) });
      },
      onEachFeature: (f, layer) => {
        layer.on("click", (ev) => {
          L.DomEvent.stopPropagation(ev);
          showTowerDetails(f);
        });
      },
    });

    // Stacking: OZ underneath, parcels, ULS, then HIFLD, then ASR on top.
    state.layers.oz.addTo(map);
    state.layers.parcels.addTo(map);
    state.layers.uls.addTo(map);
    if (state.visibility.hifld) state.layers.hifld.addTo(map);
    state.layers.towers.addTo(map);

    map.on("click", () => clearSelection());
  }

  // ── Filtering & visibility ───────────────────────────────────────────────
  function towerCarriers(feat) {
    const s = feat.properties.carriers;
    if (!s) return [];
    return s.split(/\s*;\s*/).filter(Boolean);
  }

  function applyFilters() {
    const { onlyHost, onlyOz, owner, carrier } = state.filters;

    state.layers.towers.eachLayer((layer) => {
      const f = layer.feature;
      const ownerOk = !owner || f.properties.owner_name === owner;
      const carrierOk = !carrier || towerCarriers(f).includes(carrier);
      const matches = ownerOk && carrierOk;
      layer.setOpacity(matches ? 1 : 0);
      if (layer._icon) layer._icon.style.pointerEvents = matches ? "" : "none";
    });

    [state.layers.uls, state.layers.hifld].forEach((lg) => {
      if (!lg) return;
      lg.eachLayer((layer) => {
        const f = layer.feature;
        const matches = !carrier || f.properties.licensee_name === carrier;
        layer.setOpacity(matches ? 1 : 0);
        if (layer._icon) layer._icon.style.pointerEvents = matches ? "" : "none";
      });
    });

    state.layers.parcels.eachLayer((layer) => {
      const p = layer.feature.properties;
      let show = true;
      if (onlyHost && !p.has_tower) show = false;
      if (onlyOz && !p.in_oz) show = false;
      if (show) {
        layer.setStyle(parcelStyle(layer.feature));
      } else {
        layer.setStyle({ fillOpacity: 0, weight: 0, opacity: 0 });
      }
    });

    refreshSummary();
  }

  function hostParcelsForOwner(owner) {
    const ids = new Set();
    state.towers.features.forEach((f) => {
      if (f.properties.owner_name === owner && f.properties.parcel_id) {
        ids.add(f.properties.parcel_id);
      }
    });
    return ids;
  }

  // ── Sidebar UI wiring ────────────────────────────────────────────────────
  function buildOwnerFilter() {
    const sel = document.getElementById("filter-owner");
    const owners = Array.from(
      new Set(state.towers.features.map((f) => f.properties.owner_name).filter(Boolean))
    ).sort();
    owners.forEach((o) => {
      const opt = document.createElement("option");
      opt.value = o;
      opt.textContent = o;
      sel.appendChild(opt);
    });

    // Carrier dropdown: union of ULS + HIFLD licensees and carriers on ASR towers.
    const carrierSet = new Set();
    [state.uls, state.hifld].forEach((src) => {
      if (!src) return;
      src.features.forEach((f) => {
        if (f.properties.licensee_name) carrierSet.add(f.properties.licensee_name);
      });
    });
    state.towers.features.forEach((f) => {
      towerCarriers(f).forEach((c) => carrierSet.add(c));
    });
    const carriers = Array.from(carrierSet).sort();
    const csel = document.getElementById("filter-carrier");
    carriers.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      csel.appendChild(opt);
    });
    if (carriers.length === 0) {
      csel.disabled = true;
      csel.options[0].textContent = "No ULS data loaded";
    }
  }

  function bindControls() {
    const toggle = (id, key) => {
      document.getElementById(id).addEventListener("change", (e) => {
        state.visibility[key] = e.target.checked;
        const layer = state.layers[key];
        if (e.target.checked) {
          if (!map.hasLayer(layer)) map.addLayer(layer);
        } else {
          if (map.hasLayer(layer)) map.removeLayer(layer);
        }
        refreshSummary();
      });
    };
    toggle("layer-oz", "oz");
    toggle("layer-parcels", "parcels");
    toggle("layer-towers", "towers");
    toggle("layer-uls", "uls");
    toggle("layer-hifld", "hifld");
    // Match the initial HTML check-state.
    document.getElementById("layer-hifld").checked = state.visibility.hifld;

    document.getElementById("filter-only-host").addEventListener("change", (e) => {
      state.filters.onlyHost = e.target.checked;
      applyFilters();
    });
    document.getElementById("filter-only-oz").addEventListener("change", (e) => {
      state.filters.onlyOz = e.target.checked;
      applyFilters();
    });
    document.getElementById("filter-owner").addEventListener("change", (e) => {
      state.filters.owner = e.target.value;
      applyFilters();
    });
    document.getElementById("filter-carrier").addEventListener("change", (e) => {
      state.filters.carrier = e.target.value;
      applyFilters();
    });
    document.getElementById("reset-filters").addEventListener("click", () => {
      state.filters = { onlyHost: false, onlyOz: false, owner: "", carrier: "" };
      document.getElementById("filter-only-host").checked = false;
      document.getElementById("filter-only-oz").checked = false;
      document.getElementById("filter-owner").value = "";
      document.getElementById("filter-carrier").value = "";
      applyFilters();
    });
  }

  // ── Summary counts ───────────────────────────────────────────────────────
  function refreshSummary() {
    const { carrier } = state.filters;
    const towerVis = state.visibility.towers ? countVisibleTowers() : 0;
    let ulsVis = 0;
    if (state.visibility.uls && state.uls) {
      ulsVis = carrier
        ? state.uls.features.filter((f) => f.properties.licensee_name === carrier).length
        : state.uls.features.length;
    }
    const parcelVis = state.visibility.parcels ? countVisibleParcels() : 0;
    const ozHostingCount = state.parcels
      ? state.parcels.features.filter((f) => f.properties.has_tower && f.properties.in_oz).length
      : 0;
    document.getElementById("count-towers").textContent = towerVis;
    document.getElementById("count-uls").textContent = ulsVis;
    document.getElementById("count-parcels").textContent = parcelVis.toLocaleString();
    document.getElementById("count-oz").textContent = ozHostingCount;
  }

  function countVisibleTowers() {
    const { owner, carrier } = state.filters;
    return state.towers.features.filter((f) => {
      if (owner && f.properties.owner_name !== owner) return false;
      if (carrier && !towerCarriers(f).includes(carrier)) return false;
      return true;
    }).length;
  }

  function countVisibleParcels() {
    const { onlyHost, onlyOz } = state.filters;
    let n = 0;
    state.parcels.features.forEach((f) => {
      const p = f.properties;
      if (onlyHost && !p.has_tower) return;
      if (onlyOz && !p.in_oz) return;
      n++;
    });
    return n;
  }

  // ── Details panel ────────────────────────────────────────────────────────
  function row(k, v) {
    if (v === null || v === undefined || v === "" || (typeof v === "number" && isNaN(v))) {
      return `<div class="kv-row"><span class="kv-key">${k}</span><span class="kv-val muted">—</span></div>`;
    }
    return `<div class="kv-row"><span class="kv-key">${k}</span><span class="kv-val">${escapeHtml(String(v))}</span></div>`;
  }

  function section(name) {
    return `<div class="kv-section">${name}</div>`;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
  }

  function fmtMoney(v) {
    if (v == null || v === "" || isNaN(Number(v))) return null;
    const n = Number(v);
    if (n === 0) return "$0";
    return "$" + Math.round(n).toLocaleString();
  }

  function fmtAcres(v) {
    if (v == null || v === "" || isNaN(Number(v))) return null;
    return Number(v).toFixed(2) + " ac";
  }

  function fmtMeters(v) {
    if (v == null || v === "" || isNaN(Number(v))) return null;
    const m = Number(v);
    return `${m.toFixed(1)} m (${(m * 3.281).toFixed(0)} ft)`;
  }

  function fmtLatLng(lat, lon) {
    if (lat == null || lon == null) return null;
    return `${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}`;
  }

  function showTowerDetails(f) {
    const p = f.properties;
    let parcel = null;
    if (p.parcel_id) parcel = state.parcelById.get(p.parcel_id);

    const tagBits = [];
    if (p.in_oz) tagBits.push('<span class="tag tag-oz">In OZ</span>');
    if (p.parcel_id) tagBits.push('<span class="tag tag-host">On parcel</span>');
    if (p.carrier_count) tagBits.push(`<span class="tag">${p.carrier_count} carrier${p.carrier_count === 1 ? "" : "s"}</span>`);
    const carriers = towerCarriers(f);

    const html = `
      <div style="margin-bottom: 8px">
        <strong>Tower ${escapeHtml(p.registration_number || "")}</strong>
        ${tagBits.join(" ")}
      </div>
      ${section("FCC ASR")}
      ${row("Registration #", p.registration_number)}
      ${row("Owner", p.owner_name)}
      ${row("Status", p.status_desc || p.status_code)}
      ${row("Constructed", p.date_constructed)}
      ${row("Structure type", p.structure_type_desc || p.structure_type)}
      ${row("Height (overall)", fmtMeters(p.height_overall_m))}
      ${row("Height (structure)", fmtMeters(p.height_structure_m))}
      ${row("Coordinates", fmtLatLng(p.latitude, p.longitude))}
      ${row("Listed address", p.structure_street_address)}
      ${row("City", p.structure_city)}
      ${section("Hosting parcel")}
      ${parcel
        ? row("APN", parcel.properties.apn)
          + row("Owner", parcel.properties.owner_name)
          + row("Mailing address", joinMailing(parcel.properties))
          + row("Acreage (GIS)", fmtAcres(parcel.properties.acreage_gis))
          + row("Assessed value", fmtMoney(parcel.properties.assessed_value))
          + row("Land use", parcel.properties.land_use_desc)
        : `<div class="kv-row"><span class="kv-key">Parcel</span><span class="kv-val muted">No matching parcel</span></div>`}
      ${section("Opportunity Zone")}
      ${row("In OZ tract", p.in_oz ? "Yes" : "No")}
      ${row("OZ GEOID10", p.oz_geoid)}
      ${carriers.length ? section(`Carriers on this tower (${carriers.length})`) : ""}
      ${carriers.map((c) =>
        `<div class="kv-row"><span class="kv-key">·</span><span class="kv-val">${escapeHtml(c)}</span></div>`
      ).join("")}
    `;
    setDetails(html);
    state.selected = { kind: "tower", id: p.registration_number };
    if (parcel && state.parcelLayerById.has(parcel.properties.apn)) {
      const layer = state.parcelLayerById.get(parcel.properties.apn);
      layer.setStyle(parcelSelectedStyle(parcel));
    }
  }

  function joinMailing(p) {
    const parts = [p.owner_mailing_address, p.owner_city, p.owner_state, p.owner_zip].filter(
      (x) => x !== null && x !== undefined && x !== ""
    );
    return parts.length ? parts.join(", ") : null;
  }

  function showParcelDetails(f, layer) {
    clearParcelHighlight();
    const p = f.properties;
    layer.setStyle(parcelSelectedStyle(f));
    state.selected = { kind: "parcel", id: p.apn };
    state.selectedParcelLayer = layer;

    const tagBits = [];
    if (p.has_tower && p.in_oz) {
      tagBits.push(`<span class="tag tag-host-oz">${p.tower_count || 1} tower${p.tower_count === 1 ? "" : "s"} · OZ</span>`);
    } else {
      if (p.in_oz) tagBits.push('<span class="tag tag-oz">In OZ</span>');
      if (p.has_tower) tagBits.push(`<span class="tag tag-host">${p.tower_count || 1} tower${p.tower_count === 1 ? "" : "s"}</span>`);
    }

    const onParcelTowers = state.towers.features.filter(
      (t) => t.properties.parcel_id === p.apn
    );

    const towerList = onParcelTowers.length
      ? onParcelTowers.map((t) =>
          `<div class="kv-row"><span class="kv-key">${escapeHtml(t.properties.registration_number)}</span>` +
          `<span class="kv-val">${escapeHtml(t.properties.owner_name || "")} · ` +
          `${fmtMeters(t.properties.height_overall_m) || "—"}</span></div>`
        ).join("")
      : `<div class="kv-row"><span class="kv-key">Towers</span><span class="kv-val muted">None</span></div>`;

    const html = `
      <div style="margin-bottom: 8px">
        <strong>Parcel ${escapeHtml(p.apn || p.apn_full || "")}</strong>
        ${tagBits.join(" ")}
      </div>
      ${section("Ownership")}
      ${row("Owner", p.owner_name)}
      ${row("Owner 2", p.owner_name_2)}
      ${row("Mailing address", joinMailing(p))}
      ${section("Property")}
      ${row("Situs address", p.situs_address)}
      ${row("City", p.situs_city)}
      ${row("Acreage (GIS)", fmtAcres(p.acreage_gis))}
      ${row("Acreage (recorded)", p.acreage_recorded != null && p.acreage_recorded !== "" ? Number(p.acreage_recorded).toFixed(2) + " ac" : null)}
      ${row("Land use", p.land_use_desc)}
      ${row("Has structure", p.has_structure)}
      ${row("Year built", p.structure_year && Number(p.structure_year) > 0 ? p.structure_year : null)}
      ${section("Valuation")}
      ${row("Assessed value", fmtMoney(p.assessed_value))}
      ${row("Land value", fmtMoney(p.land_value))}
      ${row("Improvement value", fmtMoney(p.improvement_value))}
      ${section("Opportunity Zone")}
      ${row("In OZ", p.in_oz ? "Yes" : "No")}
      ${onParcelTowers.length ? section("Towers on this parcel") : ""}
      ${onParcelTowers.length ? towerList : ""}
    `;
    setDetails(html);
  }

  function showHifldDetails(f) {
    const p = f.properties;
    const here = state.hifld.features.filter(
      (u) => Math.abs(u.geometry.coordinates[0] - f.geometry.coordinates[0]) < 0.0002
          && Math.abs(u.geometry.coordinates[1] - f.geometry.coordinates[1]) < 0.0002
    );
    const others = here.filter((u) => u.properties.call_sign !== p.call_sign);
    const html = `
      <div style="margin-bottom: 8px">
        <strong>HIFLD Site · ${escapeHtml(p.call_sign || "")}</strong>
        <span class="tag" style="background:#fbf5b8;color:#6b5d00;">DHS</span>
      </div>
      ${section("License")}
      ${row("Call sign", p.call_sign)}
      ${row("Licensee", p.licensee_name)}
      ${row("Status", p.license_status_desc || p.license_status)}
      ${section("Site")}
      ${row("Location #", p.location_number)}
      ${row("Address", p.location_address)}
      ${row("City", p.location_city)}
      ${row("County", p.location_county)}
      ${row("State", p.location_state)}
      ${row("Coordinates", fmtLatLng(p.latitude, p.longitude))}
      ${row("Structure type", p.structure_type_desc || p.structure_type)}
      ${row("Overall height", fmtMeters(p.height_overall_m))}
      ${row("Support height", fmtMeters(p.height_support_m))}
      ${row("ASR registration", p.tower_registration_number)}
      ${p.fcc_url ? `<div class="kv-row"><span class="kv-key">FCC link</span><span class="kv-val"><a href="${escapeHtml(p.fcc_url)}" target="_blank" rel="noopener">license summary →</a></span></div>` : ""}
      ${others.length ? section(`Other licensees at this site (${others.length})`) : ""}
      ${others.map((u) =>
        `<div class="kv-row"><span class="kv-key">${escapeHtml(u.properties.call_sign)}</span>` +
        `<span class="kv-val">${escapeHtml(u.properties.licensee_name || "")}</span></div>`
      ).join("")}
    `;
    setDetails(html);
    state.selected = { kind: "hifld", id: p.call_sign };
  }

  function showUlsDetails(f) {
    const p = f.properties;
    // List co-located licensees at this same location, since ULS sites stack.
    const here = state.uls.features.filter(
      (u) => Math.abs(u.geometry.coordinates[0] - f.geometry.coordinates[0]) < 0.0002
          && Math.abs(u.geometry.coordinates[1] - f.geometry.coordinates[1]) < 0.0002
    );
    const others = here.filter((u) => u.properties.call_sign !== p.call_sign);

    const html = `
      <div style="margin-bottom: 8px">
        <strong>ULS Site · ${escapeHtml(p.call_sign || "")}</strong>
      </div>
      ${section("License")}
      ${row("Call sign", p.call_sign)}
      ${row("Licensee", p.licensee_name)}
      ${row("Service", p.service_desc)}
      ${row("Status", p.license_status_desc || p.license_status)}
      ${row("Granted", p.grant_date)}
      ${row("Expires", p.expired_date)}
      ${section("Site")}
      ${row("Location #", p.location_number)}
      ${row("Address", p.location_address)}
      ${row("City", p.location_city)}
      ${row("County", p.location_county)}
      ${row("Coordinates", fmtLatLng(p.latitude, p.longitude))}
      ${row("Structure type", p.structure_type_desc || p.structure_type)}
      ${row("Overall height", fmtMeters(p.height_overall_m))}
      ${row("Support height", fmtMeters(p.height_support_m))}
      ${row("ASR registration", p.tower_registration_number)}
      ${section("Licensee contact")}
      ${row("Street", p.licensee_street)}
      ${row("City", `${p.licensee_city || ""}${p.licensee_state ? ", " + p.licensee_state : ""}${p.licensee_zip ? " " + p.licensee_zip : ""}`.trim() || null)}
      ${row("Phone", p.licensee_phone ? formatPhone(p.licensee_phone) : null)}
      ${others.length ? section(`Other licensees at this site (${others.length})`) : ""}
      ${others.map((u) =>
        `<div class="kv-row"><span class="kv-key">${escapeHtml(u.properties.call_sign)}</span>` +
        `<span class="kv-val">${escapeHtml(u.properties.licensee_name || "")}</span></div>`
      ).join("")}
    `;
    setDetails(html);
    state.selected = { kind: "uls", id: p.call_sign };
  }

  function formatPhone(s) {
    if (!s) return null;
    const d = String(s).replace(/\D/g, "");
    if (d.length === 10) return `(${d.slice(0,3)}) ${d.slice(3,6)}-${d.slice(6)}`;
    return s;
  }

  function showOzDetails(f) {
    const p = f.properties;
    const inside = state.parcels
      ? state.parcels.features.filter((x) => x.properties.in_oz).length
      : 0;
    const hosts = state.parcels
      ? state.parcels.features.filter((x) => x.properties.in_oz && x.properties.has_tower).length
      : 0;
    const html = `
      <div style="margin-bottom: 8px">
        <strong>Opportunity Zone</strong>
        <span class="tag tag-oz">${escapeHtml(p.geoid10 || "")}</span>
      </div>
      ${row("GEOID10", p.geoid10)}
      ${row("State", `${p.state_name} (${p.state_abbr})`)}
      ${row("State FIPS", p.state_fips)}
      ${row("County FIPS", p.county_fips)}
      ${row("Tract", p.tract)}
      ${row("Rural designation", p.rural)}
      ${section("In Graham County")}
      ${row("Parcels in tract", inside.toLocaleString())}
      ${row("Tower-hosting parcels in tract", hosts.toLocaleString())}
    `;
    setDetails(html);
    state.selected = { kind: "oz", id: p.geoid10 };
  }

  function setDetails(html) {
    document.getElementById("details-body").innerHTML = html;
  }

  function clearSelection() {
    clearParcelHighlight();
    state.selected = null;
    setDetails('<p class="muted">Click a tower or parcel to see attributes.</p>');
  }

  function clearParcelHighlight() {
    if (state.selectedParcelLayer && state.selectedParcelLayer.feature) {
      state.selectedParcelLayer.setStyle(parcelStyle(state.selectedParcelLayer.feature));
      state.selectedParcelLayer = null;
    }
  }

  // ── Boot ─────────────────────────────────────────────────────────────────
  bindControls();
  loadAll().catch((err) => {
    console.error(err);
    setDetails(
      `<p class="muted">Failed to load data: ${escapeHtml(err.message)}.<br>` +
      `Did you run <code>scripts/preprocess.py</code> and start the server from the project root?</p>`
    );
  });
})();
