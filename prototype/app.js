// PROTOTYPE — throwaway. Lead-centric triage redesign (ADR-061). Delete /prototype when done.
//
// One route shell, four surfaces (#/map, #/candidates, #/leads, #/lead/:key).
// The ONLY thing the ?variant= switcher flips is FILTER PLACEMENT:
//   variant=topbar  -> slim top filter bar + "More" popover   (Variant A)
//   variant=drawer  -> decluttered collapsible left drawer     (Variant B)
// Everything else (map pivot to structures, candidates table, kanban, lead page)
// is held constant on purpose — the open question is "where do the filters go".
// Map instance is kept alive across route changes (parked off-DOM, never destroyed).

import {
  LEADS, LEAD_BY_KEY, towerGeoJSON, STATUS_LABEL, KANBAN_LANES, KIND_LABEL,
  ALL_STATES, ALL_COUNTIES, KIND_VALUES,
} from './mock.js';

const VARIANTS = ['topbar', 'drawer'];
const VARIANT_NAME = { topbar: 'A — Top filter bar', drawer: 'B — Left drawer' };
const TIERS = ['high', 'medium', 'low', 'none'];

// ---- in-memory state (no persistence — that's the point) ----
const filters = {
  states: new Set(), tiers: new Set(), kinds: new Set(), counties: new Set(),
  structureTypes: new Set(), oz: false, qct: false, poverty: false,
  scoreMin: 0, portfolioMin: 1, assessedMin: 0, heightMin: 0, structCountMin: 1, activeOnly: false,
};
let openQuick = null;        // which top-bar popover is open
let miniMap = null;          // lead-detail mini map (recreated per lead)

// ---- tiny DOM helper ----
function E(tag, attrs = {}, kids = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of [].concat(kids)) if (c != null) n.append(c.nodeType ? c : document.createTextNode(c));
  return n;
}
const money = (n) => (n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}K` : `$${n}`);

// ---- routing ----
const variant = () => (VARIANTS.includes(new URLSearchParams(location.search).get('variant')) ? new URLSearchParams(location.search).get('variant') : 'topbar');
function parseRoute() {
  const h = (location.hash.replace(/^#/, '') || '/map').split('/').filter(Boolean);
  if (h[0] === 'lead' && h[1]) return { name: 'lead', key: h[1] };
  return { name: ['map', 'candidates', 'leads'].includes(h[0]) ? h[0] : 'map' };
}
const go = (hash) => { location.hash = hash; };
function setVariant(v) {
  const u = new URL(location.href); u.searchParams.set('variant', v); history.replaceState(null, '', u); render();
}

// ---- filter predicate ----
function matches(l) {
  if (filters.states.size && !l.states.some((s) => filters.states.has(s))) return false;
  if (filters.tiers.size && !filters.tiers.has(l.distress.tier)) return false;
  if (filters.kinds.size && !filters.kinds.has(l.kind)) return false;
  if (filters.counties.size && !l.counties.some((c) => filters.counties.has(c))) return false;
  if (filters.oz && !l.distress.oz) return false;
  if (filters.qct && !l.distress.qct) return false;
  if (filters.poverty && !l.distress.poverty) return false;
  if (l.score < filters.scoreMin) return false;
  if (l.parcelCount < filters.portfolioMin) return false;
  if (l.totalAssessed < filters.assessedMin) return false;
  if (l.maxHeight < filters.heightMin) return false;
  if (filters.activeOnly && l.activeTowerCount === 0) return false;
  if (l.towerCount + l.solarCount < filters.structCountMin) return false;
  if (filters.structureTypes.size) {
    const ok = (filters.structureTypes.has('tower') && l.towerCount > 0) || (filters.structureTypes.has('solar') && l.solarCount > 0);
    if (!ok) return false;
  }
  return true;
}
const matched = () => LEADS.filter(matches);
const candidates = () => matched().filter((l) => l.status === 'new').sort((a, b) => b.score - a.score);
const worklist = () => matched().filter((l) => l.status !== 'new');

// ============ shell (built once) ============
const app = document.getElementById('app');
let nav, filterTop, drawerHost, contentHost, mapNode, mapPark;
let map = null;

function buildShell() {
  nav = E('nav', { class: 'topnav' });
  filterTop = E('div', { id: 'filter-top' });
  drawerHost = E('div', { id: 'drawer-host' });
  contentHost = E('div', { class: 'scroll', id: 'content', style: 'position:relative' });
  const surface = E('div', { class: 'surface' }, [drawerHost, contentHost]);
  app.append(nav, filterTop, surface);

  mapPark = E('div', { id: 'map-park', style: 'display:none' });
  mapNode = E('div', { id: 'map' });
  mapPark.append(mapNode);
  document.body.append(mapPark);
  document.body.append(switcher());

  window.addEventListener('hashchange', render);
  window.addEventListener('resize', () => map && map.resize());
  window.addEventListener('keydown', (e) => {
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
    if (e.key === 'ArrowRight') setVariant(VARIANTS[(VARIANTS.indexOf(variant()) + 1) % 2]);
    if (e.key === 'ArrowLeft') setVariant(VARIANTS[(VARIANTS.indexOf(variant()) + 1) % 2]);
  });
}

function ensureMap() {
  if (map) return;
  map = new maplibregl.Map({
    container: mapNode,
    style: {
      version: 8,
      sources: { carto: { type: 'raster', tiles: ['a', 'b', 'c', 'd'].map((s) => `https://${s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png`), tileSize: 256, attribution: '© CARTO © OpenStreetMap' } },
      layers: [{ id: 'bg', type: 'raster', source: 'carto' }],
    },
    center: [-92, 37], zoom: 3.4,
  });
  map.on('load', () => {
    map.addSource('towers', { type: 'geojson', data: towerGeoJSON(matched()), cluster: true, clusterRadius: 44 });
    map.addLayer({ id: 'clusters', type: 'circle', source: 'towers', filter: ['has', 'point_count'],
      paint: { 'circle-color': '#1769c4', 'circle-opacity': 0.85, 'circle-radius': ['step', ['get', 'point_count'], 14, 5, 19, 15, 26] } });
    map.addLayer({ id: 'cluster-count', type: 'symbol', source: 'towers', filter: ['has', 'point_count'],
      layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12 }, paint: { 'text-color': '#fff' } });
    map.addLayer({ id: 'tower', type: 'circle', source: 'towers', filter: ['!', ['has', 'point_count']],
      paint: { 'circle-radius': 6, 'circle-stroke-width': 1.5, 'circle-stroke-color': '#fff',
        'circle-color': ['match', ['get', 'status'], 'new', '#8893a0', 'researching', '#b8860b', 'contacted', '#1769c4', 'interested', '#6f42c1', 'in_business', '#2e7d4f', '#b0392b'] } });

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });
    map.on('mouseenter', 'tower', (e) => {
      map.getCanvas().style.cursor = 'pointer';
      const p = e.features[0].properties;
      popup.setLngLat(e.features[0].geometry.coordinates).setHTML(`<b>${p.ownerName}</b><br>ASR ${p.asr} · ${p.height} ft · ${p.state}`).addTo(map);
    });
    map.on('mouseleave', 'tower', () => { map.getCanvas().style.cursor = ''; popup.remove(); });
    map.on('click', 'tower', (e) => go(`#/lead/${e.features[0].properties.ownerKey}`));
    map.on('mouseenter', 'clusters', () => (map.getCanvas().style.cursor = 'pointer'));
    map.on('mouseleave', 'clusters', () => (map.getCanvas().style.cursor = ''));
    map.on('click', 'clusters', (e) => {
      const f = map.queryRenderedFeatures(e.point, { layers: ['clusters'] })[0];
      map.getSource('towers').getClusterExpansionZoom(f.properties.cluster_id).then((z) => map.easeTo({ center: f.geometry.coordinates, zoom: z }));
    });
  });
}
function refreshMapData() {
  if (map && map.getSource('towers')) map.getSource('towers').setData(towerGeoJSON(matched()));
}

// ============ render ============
function render() {
  const r = parseRoute();
  renderNav(r);
  renderFilterChrome(r);

  // keep the live map alive: park it unless we're on /map
  if (r.name !== 'map' && mapNode.parentElement !== mapPark) mapPark.append(mapNode);
  contentHost.innerHTML = '';
  // the map fills its host (flex column); other surfaces scroll as a block
  contentHost.style.display = r.name === 'map' ? 'flex' : '';
  contentHost.style.flexDirection = r.name === 'map' ? 'column' : '';
  contentHost.style.overflow = r.name === 'map' ? 'hidden' : '';

  if (r.name === 'map') {
    contentHost.append(mapNode, E('div', { class: 'map-hint' }, 'Structures-first · click a tower → its landowner Lead · all 4 anchors at once'));
    ensureMap();
    requestAnimationFrame(() => map && map.resize());
    refreshMapData();
  } else if (r.name === 'candidates') renderCandidates();
  else if (r.name === 'leads') renderKanban();
  else if (r.name === 'lead') renderLead(r.key);

  refreshMapData();
}

function renderNav(r) {
  nav.innerHTML = '';
  nav.append(E('span', { class: 'brand', html: 'Ground-Lease Triage <small>· prototype</small>' }));
  const tab = (key, label, count) => {
    const t = E('button', { class: 'navtab' + (r.name === key ? ' on' : ''), onclick: () => go('#/' + key) }, [label]);
    if (count != null) t.append(E('span', { class: 'badge' }, String(count)));
    return t;
  };
  nav.append(tab('map', 'Map'), tab('candidates', 'Candidates', candidates().length), tab('leads', 'My Leads', worklist().length));
  nav.append(E('span', { class: 'spacer' }));
  nav.append(E('span', { class: 'sub', style: 'font-size:11px', html: 'Lead = cross-state landowner · ADR-061' }));
}

// ---------- shared filter controls ----------
function chipSet(values, set, labelFn) {
  return E('div', { class: 'chips' }, values.map((v) =>
    E('button', { class: 'chip' + (set.has(v) ? ' on' : ''), onclick: () => { set.has(v) ? set.delete(v) : set.add(v); render(); } }, labelFn(v))));
}
function check(label, key) {
  return E('label', { class: 'checkrow' }, [
    E('input', { type: 'checkbox', ...(filters[key] ? { checked: true } : {}), onchange: (e) => { filters[key] = e.target.checked; render(); } }),
    E('span', {}, label)]);
}
function range(label, key, min, max, step, fmt) {
  const v = filters[key];
  return E('div', {}, [
    E('span', { class: 'flabel' }, `${label}: ${fmt ? fmt(v) : v}`),
    E('input', { type: 'range', min, max, step, value: v, oninput: (e) => { filters[key] = Number(e.target.value); render(); } })]);
}
const cLabel = (c) => { const [s, n] = c.split(':'); return `${n} (${s})`; };

const ctl = {
  state: () => E('div', {}, [E('span', { class: 'flabel' }, 'State'), chipSet(ALL_STATES, filters.states, (v) => v)]),
  county: () => E('div', {}, [E('span', { class: 'flabel' }, 'County'), chipSet(ALL_COUNTIES, filters.counties, cLabel)]),
  distress: () => E('div', {}, [
    E('span', { class: 'flabel' }, 'Distress tier'), chipSet(TIERS, filters.tiers, (v) => v[0].toUpperCase() + v.slice(1)),
    check('In Opportunity Zone', 'oz'), check('Qualified Census Tract', 'qct'), check('Persistent poverty', 'poverty')]),
  owner: () => E('div', {}, [
    E('span', { class: 'flabel' }, 'Owner kind'), chipSet(KIND_VALUES, filters.kinds, (v) => KIND_LABEL[v]),
    range('Portfolio (min parcels)', 'portfolioMin', 1, 5, 1),
    range('Total assessed (min)', 'assessedMin', 0, 2000000, 100000, money)]),
  structure: () => E('div', {}, [
    E('span', { class: 'flabel' }, 'Structure type'), chipSet(['tower', 'solar'], filters.structureTypes, (v) => v[0].toUpperCase() + v.slice(1)),
    range('Tower height (min ft)', 'heightMin', 0, 320, 10),
    range('Structure count (min)', 'structCountMin', 1, 4, 1), check('Active towers only', 'activeOnly')]),
  score: () => E('div', {}, [range('Interestingness score (min)', 'scoreMin', 0, 1, 0.05, (v) => v.toFixed(2))]),
};

function renderFilterChrome(r) {
  filterTop.innerHTML = ''; drawerHost.innerHTML = '';
  if (r.name === 'lead') return;                 // no filters on the detail page
  if (variant() === 'topbar') buildTopBar(); else buildDrawer();
}

function buildTopBar() {
  const bar = E('div', { class: 'filterbar' });
  const activeCount = { State: filters.states.size, Distress: filters.tiers.size + filters.oz + filters.qct + filters.poverty, Structure: filters.structureTypes.size + (filters.heightMin > 0) + filters.activeOnly, Score: filters.scoreMin > 0 ? 1 : 0 };
  const quick = (label, key) => {
    const b = E('button', { class: 'fbtn' + (activeCount[label] ? ' active' : ''), onclick: (e) => { e.stopPropagation(); toggleQuick(key, b); } },
      [label + (activeCount[label] ? ` · ${activeCount[label]}` : ''), E('span', { class: 'chev' }, '▾')]);
    return b;
  };
  bar.append(quick('State', 'state'), quick('Distress', 'distress'), quick('Structure', 'structure'), quick('Score', 'score'));
  const more = E('button', { class: 'fbtn more', onclick: (e) => { e.stopPropagation(); toggleQuick('more', more); } }, ['⊕ More filters', E('span', { class: 'chev' }, '▾')]);
  bar.append(more);
  filterTop.append(bar);
  document.addEventListener('click', closeQuick, { once: true });
}
function closeQuick() { const p = document.getElementById('quick-pop'); if (p) p.remove(); openQuick = null; }
function toggleQuick(key, btn) {
  const existing = document.getElementById('quick-pop');
  if (existing && openQuick === key) { closeQuick(); return; }
  closeQuick(); openQuick = key;
  const pop = E('div', { class: 'popover', id: 'quick-pop', onclick: (e) => e.stopPropagation() });
  if (key === 'more') pop.append(ctl.owner(), ctl.county());
  else pop.append(ctl[key]());
  const rect = btn.getBoundingClientRect();
  pop.style.top = rect.bottom + 6 + 'px';
  pop.style.left = Math.min(rect.left, window.innerWidth - 340) + 'px';
  pop.style.right = 'auto';
  document.body.append(pop);
  setTimeout(() => document.addEventListener('click', closeQuick, { once: true }), 0);
}

let drawerCollapsed = false;
function buildDrawer() {
  const d = E('aside', { class: 'drawer' + (drawerCollapsed ? ' collapsed' : '') });
  d.append(E('div', { class: 'drawer-head' }, [
    E('h3', {}, 'Filters'),
    E('button', { class: 'collapse-btn', title: 'Collapse', onclick: () => { drawerCollapsed = !drawerCollapsed; render(); } }, drawerCollapsed ? '»' : '«')]));
  const body = E('div', { class: 'drawer-body' });
  body.append(ctl.score());                       // high-use, top-level
  const group = (title, content, open = true) => {
    const det = E('details', { class: 'fgroup', ...(open ? { open: true } : {}) });
    det.append(E('summary', {}, title), E('div', { class: 'fbody' }, content));
    return det;
  };
  body.append(
    group('Location', [ctl.state(), ctl.county()]),
    group('Distress', ctl.distress()),
    group('Owner', E('div', {}, [E('span', { class: 'flabel' }, 'Owner kind'), chipSet(KIND_VALUES, filters.kinds, (v) => KIND_LABEL[v])])),
    group('Structure', E('div', {}, [E('span', { class: 'flabel' }, 'Type'), chipSet(['tower', 'solar'], filters.structureTypes, (v) => v[0].toUpperCase() + v.slice(1))])),
    group('Advanced', [range('Portfolio (min parcels)', 'portfolioMin', 1, 5, 1), range('Total assessed (min)', 'assessedMin', 0, 2000000, 100000, money), range('Tower height (min ft)', 'heightMin', 0, 320, 10), range('Structure count (min)', 'structCountMin', 1, 4, 1), check('Active towers only', 'activeOnly')], false));
  d.append(body);
  drawerHost.append(d);
}

// ---------- Candidates ----------
function statusDot(s) { return E('span', { class: 'status-dot', style: `background:var(--s-${s})` }); }
function distressCell(d) {
  const cls = d.tier === 'high' ? 'distress-high' : d.tier === 'medium' ? 'distress-medium' : '';
  const flags = [d.oz && 'OZ', d.qct && 'QCT', d.poverty && 'PP'].filter(Boolean).join(' ');
  return E('span', { class: cls }, `${d.tier}${flags ? ' · ' + flags : ''}`);
}
function renderCandidates() {
  const rows = candidates();
  const wrap = E('div', { class: 'candidates' });
  wrap.append(E('h2', {}, 'Candidates'), E('div', { class: 'sub' }, `${rows.length} landowners at status “New”, ranked by interestingness — the discovery surface. Open one to start working it.`));
  const t = E('table', { class: 'leads' });
  t.append(E('thead', {}, E('tr', {}, ['', 'Owner', 'Kind', 'States', 'Distress', 'Towers', 'Assessed', 'Score'].map((h) => E('th', { class: h === 'Assessed' || h === 'Towers' || h === 'Score' ? 'num-cell' : '' }, h)))));
  const tb = E('tbody', {});
  rows.forEach((l, i) => {
    tb.append(E('tr', { onclick: () => go(`#/lead/${l.key}`) }, [
      E('td', { class: 'num-cell readonly' }, String(i + 1)),
      E('td', {}, [statusDot(l.status), l.name]),
      E('td', {}, KIND_LABEL[l.kind]),
      E('td', {}, l.states.map((s) => E('span', { class: 'tag state', style: 'margin-right:3px' }, s)).concat(l.crossState ? [E('span', { class: 'tag x' }, 'multi-state')] : [])),
      E('td', {}, distressCell(l.distress)),
      E('td', { class: 'num-cell' }, String(l.towerCount)),
      E('td', { class: 'num-cell' }, money(l.totalAssessed)),
      E('td', { class: 'num-cell' }, [E('span', { class: 'scorebar', style: `width:${Math.round(l.score * 44)}px;margin-right:6px` }), l.score.toFixed(2)])]));
  });
  t.append(tb); wrap.append(t); contentHost.append(wrap);
}

// ---------- Kanban ----------
function renderKanban() {
  const board = E('div', { class: 'kanban' });
  const list = worklist();
  for (const lane of KANBAN_LANES) {
    const inLane = list.filter((l) => l.status === lane);
    const closed = lane === 'uninterested';
    const col = E('div', { class: 'lane' + (closed ? ' closed' : '') });
    col.append(E('div', { class: 'lane-head', style: `border-color:var(--s-${lane})` }, [STATUS_LABEL[lane], E('span', { class: 'tag' }, String(inLane.length))]));
    const body = E('div', { class: 'lane-body' });
    body.addEventListener('dragover', (e) => { e.preventDefault(); col.classList.add('dragover'); });
    body.addEventListener('dragleave', () => col.classList.remove('dragover'));
    body.addEventListener('drop', (e) => { e.preventDefault(); col.classList.remove('dragover'); const key = e.dataTransfer.getData('text'); if (LEAD_BY_KEY[key]) { LEAD_BY_KEY[key].status = lane; render(); } });
    inLane.forEach((l) => {
      const card = E('div', { class: 'card', draggable: 'true', onclick: () => go(`#/lead/${l.key}`) }, [
        E('div', { class: 'cname' }, l.name),
        E('div', { class: 'cmeta' }, [
          E('span', {}, KIND_LABEL[l.kind]),
          E('span', {}, `${l.states.join('/')}`),
          E('span', {}, `${l.towerCount} twr`),
          l.distress.tier === 'high' ? E('span', { class: 'distress-high' }, 'high distress') : null])]);
      card.addEventListener('dragstart', (e) => e.dataTransfer.setData('text', l.key));
      body.append(card);
    });
    col.append(body); board.append(col);
  }
  contentHost.append(E('div', { class: 'candidates', style: 'padding-bottom:8px' }, [E('h2', {}, 'My Leads'), E('div', { class: 'sub' }, 'Owners you’ve advanced off “New”. Drag a card between lanes to change status (auto-logged). New owners live in Candidates.')]));
  contentHost.append(board);
}

// ---------- Lead detail ----------
const STATUS_FLOW = ['new', 'researching', 'contacted', 'interested', 'in_business', 'uninterested'];
function renderLead(key) {
  const l = LEAD_BY_KEY[key];
  if (!l) { contentHost.append(E('div', { class: 'candidates' }, 'Lead not found.')); return; }
  const grid = E('div', { class: 'lead' });

  // header
  const header = E('div', { class: 'lead-header' }, [
    E('a', { class: 'backlink', onclick: () => history.back() }, '‹ back'),
    statusDot(l.status), E('h1', {}, l.name),
    E('span', { class: 'tag' }, KIND_LABEL[l.kind]),
    ...l.states.map((s) => E('span', { class: 'tag state' }, s)),
    l.crossState ? E('span', { class: 'tag x' }, 'cross-state lead') : null]);
  grid.append(header);

  // LEFT column: why interesting + holdings
  const left = E('div', { class: 'col' });
  left.append(E('div', { class: 'card-box' }, [
    E('h3', {}, 'Why this lead'),
    E('div', { class: 'statpills' }, [
      pill(l.score.toFixed(2), 'score'), pill(l.parcelCount, 'parcels'), pill(l.towerCount, 'towers'),
      pill(money(l.totalAssessed), 'assessed'), pill(l.maxHeight + 'ft', 'tallest')]),
    E('div', { style: 'margin-top:10px' }, [
      E('span', { class: 'flabel' }, 'Distress'),
      E('div', {}, distressCell(l.distress))])]));

  const holdings = E('div', { class: 'card-box' }, [E('h3', {}, `Holdings · ${l.parcelCount} parcels across ${l.states.length} state(s)`)]);
  const mini = E('div', { class: 'mini-map' }); holdings.append(mini);
  l.parcels.forEach((p) => {
    holdings.append(E('div', { class: 'holding' }, [
      E('div', { class: 'hrow' }, [E('b', {}, `${p.county} Co, ${p.state}`), E('span', { class: 'readonly' }, money(p.assessed) + ' · ' + p.acreage + ' ac')]),
      E('div', { class: 'readonly', style: 'font-size:12px' }, p.situs),
      ...p.towers.map((t) => E('div', { class: 'twr' }, `▲ Tower ASR ${t.asr} — ${t.height} ft ${t.type}${t.active ? '' : ' (inactive)'}`)),
      ...(p.solar || []).map(() => E('div', { class: 'twr' }, '☀ Solar facility'))]));
  });
  left.append(holdings);

  // RIGHT column: status, contact, attempts, notes
  const right = E('div', { class: 'col' });
  right.append(E('div', { class: 'card-box' }, [
    E('h3', {}, 'Status'),
    E('div', { class: 'statusbtns' }, STATUS_FLOW.map((s) =>
      E('button', { class: 'sbtn' + (l.status === s ? ' on' : ''), style: l.status === s ? `background:var(--s-${s})` : '', onclick: () => { l.status = s; render(); } }, STATUS_LABEL[s]))),
    E('div', { class: 'sub', style: 'margin-top:8px' }, 'New → Researching → Contacted → (Interested → In Business) | Uninterested')]));

  const c = l.contact;
  right.append(E('div', { class: 'card-box' }, [
    E('h3', {}, 'Contact'),
    E('div', { class: 'kv' }, [
      E('dt', {}, 'Mailing'), E('dd', { class: 'readonly' }, `${c && l.mailing.addr}, ${l.mailing.city}, ${l.mailing.state} ${l.mailing.zip}`)]),
    field('Contact name', l.contact, 'name'), field('Phone', l.contact, 'phone'), field('Email', l.contact, 'email'),
    E('span', { class: 'flabel' }, 'Best channel'),
    selectField(l.contact, 'channel', ['', 'phone', 'mail', 'email', 'text', 'in-person'])]));

  // contact attempts
  const att = E('div', { class: 'card-box' }, [E('h3', {}, 'Contact attempts')]);
  if (!l.contactAttempts.length) att.append(E('div', { class: 'sub' }, 'No attempts logged yet.'));
  l.contactAttempts.forEach((a) => att.append(E('div', { class: 'attempt' }, [E('span', { class: 'readonly' }, a.date), E('span', {}, a.channel), E('span', {}, a.outcome)])));
  // quick add
  const chan = E('select', { class: 'field', style: 'width:auto' }, ['phone', 'mail', 'email', 'text', 'in-person'].map((o) => E('option', {}, o)));
  const out = E('select', { class: 'field', style: 'width:auto' }, ['no answer', 'left voicemail', 'bad number', 'spoke–interested', 'spoke–not interested', 'sent', 'returned', 'meeting'].map((o) => E('option', {}, o)));
  att.append(E('div', { style: 'display:flex;gap:6px;margin-top:8px;align-items:center;flex-wrap:wrap' }, [
    chan, out, E('button', { class: 'sbtn', onclick: () => { l.contactAttempts.unshift({ date: '2026-05-30', channel: chan.value, outcome: out.value }); render(); } }, '+ log attempt')]));
  right.append(att);

  right.append(E('div', { class: 'card-box' }, [
    E('h3', {}, 'Notes'),
    E('textarea', { class: 'field', placeholder: 'Free-text notes…', oninput: (e) => (l.notes = e.target.value) }, l.notes)]));

  grid.append(left, right); contentHost.append(grid);

  // mini-map of this lead's towers
  if (miniMap) { try { miniMap.remove(); } catch (e) {} miniMap = null; }
  const pts = towerGeoJSON([l]);
  requestAnimationFrame(() => {
    miniMap = new maplibregl.Map({ container: mini, style: { version: 8, sources: { carto: { type: 'raster', tiles: ['a', 'b', 'c'].map((s) => `https://${s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png`), tileSize: 256 } }, layers: [{ id: 'bg', type: 'raster', source: 'carto' }] }, center: pts.features[0]?.geometry.coordinates || [-92, 37], zoom: 5, interactive: true, attributionControl: false });
    miniMap.on('load', () => {
      pts.features.forEach((f) => new maplibregl.Marker({ color: '#1769c4' }).setLngLat(f.geometry.coordinates).addTo(miniMap));
      if (pts.features.length > 1) {
        const b = new maplibregl.LngLatBounds();
        pts.features.forEach((f) => b.extend(f.geometry.coordinates));
        miniMap.fitBounds(b, { padding: 40, maxZoom: 7, duration: 0 });
      }
    });
  });
}
function pill(v, label) { return E('div', { class: 'statpill' }, [E('b', {}, String(v)), E('span', {}, label)]); }
function field(label, obj, key) {
  return E('div', {}, [E('span', { class: 'flabel' }, label), E('input', { class: 'field', value: obj[key] || '', placeholder: '—', oninput: (e) => (obj[key] = e.target.value) })]);
}
function selectField(obj, key, opts) {
  const s = E('select', { class: 'field', onchange: (e) => (obj[key] = e.target.value) }, opts.map((o) => E('option', { value: o, ...(obj[key] === o ? { selected: true } : {}) }, o || '—')));
  return s;
}

// ---------- variant switcher ----------
function switcher() {
  const bar = E('div', { class: 'switcher' });
  const label = E('span', { class: 'label' });
  const sync = () => (label.innerHTML = `<b>${VARIANT_NAME[variant()]}</b>`);
  const flip = () => setVariant(VARIANTS[(VARIANTS.indexOf(variant()) + 1) % 2]);
  bar.append(
    E('button', { class: 'arrow', onclick: flip }, '‹'),
    label,
    E('button', { class: 'arrow', onclick: flip }, '›'),
    E('span', { class: 'note' }, 'filter placement · ← →'));
  // keep label fresh across renders
  new MutationObserver(sync).observe(document.body, { attributes: true, attributeFilter: ['data-v'] });
  sync();
  setInterval(sync, 400);
  return bar;
}

// ---------- boot ----------
buildShell();
render();
