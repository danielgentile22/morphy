// PROTOTYPE — throwaway mock data. Delete with the rest of /prototype.
// ~24 cross-state landowner Leads across the 4 anchor states (AR/MT/FL/WV).
// Spread across the status ladder so both Candidates (New) and the kanban populate.

// State centroids (rough) for scattering mock tower points.
const STATE_CENTER = {
  AR: [-92.4, 34.8],
  MT: [-109.6, 46.9],
  FL: [-81.6, 28.4],
  WV: [-80.6, 38.9],
};

const COUNTIES = {
  AR: ['Pulaski', 'Washington', 'Benton', 'Garland', 'Craighead'],
  MT: ['Yellowstone', 'Missoula', 'Flathead', 'Gallatin', 'Cascade'],
  FL: ['Miami-Dade', 'Polk', 'Marion', 'Lake', 'Columbia'],
  WV: ['McDowell', 'Kanawha', 'Mingo', 'Logan', 'Raleigh'],
};

// Deterministic pseudo-scatter so tower points don't stack.
function scatter(state, seed) {
  const [lon, lat] = STATE_CENTER[state];
  const dx = (((seed * 73) % 100) / 100 - 0.5) * 2.2;
  const dy = (((seed * 41) % 100) / 100 - 0.5) * 1.6;
  return [lon + dx, lat + dy];
}

let _asr = 1090000;
function tower(state, seed, { height = 90, type = 'Monopole', active = true } = {}) {
  _asr += 137;
  const [lon, lat] = scatter(state, seed);
  return { asr: String(_asr), height, type, active, lon, lat };
}

function parcel(state, seed, assessed, acreage, towers = [], solar = []) {
  const counties = COUNTIES[state];
  const county = counties[seed % counties.length];
  return {
    id: `${state}-${10000 + seed}`,
    state,
    county,
    situs: `${100 + seed} County Rd, ${county} Co, ${state}`,
    assessed,
    acreage,
    towers,
    solar,
  };
}

// status: new | researching | contacted | interested | in_business | uninterested
// kind:   individual | llc | corporation | government | trust
const RAW = [
  {
    key: 'weyerhaeuser-co',
    name: 'WEYERHAEUSER CO',
    kind: 'corporation',
    status: 'interested',
    score: 0.94,
    distress: { tier: 'high', oz: true, qct: false, poverty: true },
    mailing: { addr: '220 Occidental Ave S', city: 'Seattle', state: 'WA', zip: '98104' },
    contact: { name: 'Land Mgmt Dept', phone: '206-555-0101', email: 'land@wy.example', channel: 'phone' },
    contactAttempts: [
      { date: '2026-05-22', channel: 'phone', outcome: 'left voicemail' },
      { date: '2026-05-26', channel: 'phone', outcome: 'spoke–interested' },
    ],
    notes: 'Big timber holder. Regional land manager open to a call about the AR + MT sites. Wants a one-pager first.',
    parcels: [
      parcel('AR', 3, 1850000, 640, [tower('AR', 3, { height: 320, type: 'Lattice' })]),
      parcel('AR', 7, 920000, 410, [tower('AR', 7, { height: 180 })]),
      parcel('MT', 11, 1200000, 1200, [tower('MT', 11, { height: 250, type: 'Guyed' })]),
    ],
  },
  {
    key: 'bnsf-railway',
    name: 'BNSF RAILWAY CO',
    kind: 'corporation',
    status: 'contacted',
    score: 0.91,
    distress: { tier: 'high', oz: false, qct: true, poverty: false },
    mailing: { addr: '2650 Lou Menk Dr', city: 'Fort Worth', state: 'TX', zip: '76131' },
    contact: { name: '', phone: '', email: '', channel: '' },
    contactAttempts: [{ date: '2026-05-28', channel: 'mail', outcome: 'sent' }],
    notes: 'Rail right-of-way parcels host towers in AR and MT. Corporate real-estate group is the gatekeeper.',
    parcels: [
      parcel('AR', 13, 540000, 22, [tower('AR', 13, { height: 150 })]),
      parcel('MT', 17, 610000, 35, [tower('MT', 17, { height: 199 }), tower('MT', 18, { height: 120, active: false })]),
    ],
  },
  {
    key: 'smith-family-trust',
    name: 'SMITH FAMILY TRUST',
    kind: 'trust',
    status: 'researching',
    score: 0.88,
    distress: { tier: 'medium', oz: false, qct: false, poverty: true },
    mailing: { addr: '14 Ridgecrest Ln', city: 'Hot Springs', state: 'AR', zip: '71901' },
    contact: { name: 'Dale Smith (trustee)', phone: '501-555-0144', email: '', channel: 'phone' },
    contactAttempts: [],
    notes: 'Single high-value parcel, lattice tower. Trustee name found via county records — no phone confirmed yet.',
    parcels: [parcel('AR', 21, 410000, 160, [tower('AR', 21, { height: 280, type: 'Lattice' })])],
  },
  {
    key: 'state-of-montana',
    name: 'STATE OF MONTANA',
    kind: 'government',
    status: 'uninterested',
    score: 0.62,
    distress: { tier: 'low', oz: false, qct: false, poverty: false },
    mailing: { addr: '1301 E 6th Ave', city: 'Helena', state: 'MT', zip: '59601' },
    contact: { name: 'State Lands Office', phone: '406-555-0190', email: 'lands@mt.example', channel: 'phone' },
    contactAttempts: [{ date: '2026-05-20', channel: 'phone', outcome: 'spoke–not interested' }],
    notes: 'State trust land. Leases handled centrally; not renegotiable through us. Marked uninterested.',
    parcels: [
      parcel('MT', 29, 0, 5400, [tower('MT', 29, { height: 300, type: 'Guyed' })]),
      parcel('MT', 31, 0, 2100, [tower('MT', 31, { height: 140 })]),
    ],
  },
  {
    key: 'gulfstream-holdings-llc',
    name: 'GULFSTREAM HOLDINGS LLC',
    kind: 'llc',
    status: 'in_business',
    score: 0.9,
    distress: { tier: 'high', oz: true, qct: true, poverty: false },
    mailing: { addr: '900 Biscayne Blvd', city: 'Miami', state: 'FL', zip: '33132' },
    contact: { name: 'R. Alvarez', phone: '305-555-0177', email: 'ra@gulfstream.example', channel: 'email' },
    contactAttempts: [
      { date: '2026-05-10', channel: 'email', outcome: 'sent' },
      { date: '2026-05-14', channel: 'phone', outcome: 'spoke–interested' },
      { date: '2026-05-27', channel: 'in-person', outcome: 'meeting' },
    ],
    notes: 'Deal in progress. Reviewing draft addendum for the Polk Co tower. Hot lead.',
    parcels: [
      parcel('FL', 37, 2400000, 12, [tower('FL', 37, { height: 220, type: 'Monopole' })]),
      parcel('FL', 41, 1100000, 8, [tower('FL', 41, { height: 160 })], [{ id: 'sol-FL-1' }]),
    ],
  },
  // Cross-state individual
  {
    key: 'james-r-carter',
    name: 'CARTER, JAMES R',
    kind: 'individual',
    status: 'new',
    score: 0.86,
    distress: { tier: 'high', oz: false, qct: false, poverty: true },
    mailing: { addr: '88 Hollow Rd', city: 'Welch', state: 'WV', zip: '24801' },
    contact: { name: '', phone: '', email: '', channel: '' },
    contactAttempts: [],
    notes: '',
    parcels: [
      parcel('WV', 47, 95000, 220, [tower('WV', 47, { height: 260, type: 'Lattice' })]),
      parcel('WV', 49, 60000, 140, [tower('WV', 49, { height: 110 })]),
    ],
  },
];

// --- A batch of plain New candidates to make the discovery list feel deep ---
const KINDS = ['individual', 'llc', 'individual', 'trust', 'individual', 'llc'];
const NAMES = [
  'APPALACHIAN LAND CO LLC', 'MOUNTAIN VIEW FARMS', 'OZARK TIMBER LLC', 'DELTA AG HOLDINGS',
  'BIG SKY CATTLE CO', 'RIVERSIDE PROPERTIES LLC', 'PINE RIDGE TRUST', 'COASTAL PALMS LLC',
  'HARLAN, BETTY J', 'NGUYEN, TRAN', 'FLATHEAD RANCH LLC', 'SUNCOAST GROVES INC',
  'KANAWHA HOLLOW LLC', 'BAYOU LAND TRUST', 'SUMMIT WIRELESS SITES LLC', 'GREEN ACRES FARM',
  'MARION CITRUS CO', 'CLEARWATER HOLDINGS LLC',
];
const STATES = ['AR', 'MT', 'FL', 'WV'];
const TIERS = ['high', 'medium', 'low', 'none'];

NAMES.forEach((name, i) => {
  const st = STATES[i % 4];
  const tier = TIERS[i % 4];
  const nParcels = 1 + (i % 3);
  const parcels = [];
  for (let p = 0; p < nParcels; p++) {
    const seed = 50 + i * 5 + p;
    parcels.push(
      parcel(st, seed, 80000 + ((i * 37) % 50) * 9000, 40 + ((i * 13) % 30) * 20, [
        tower(st, seed, { height: 90 + ((i * 17) % 24) * 10, active: i % 7 !== 0 }),
      ]),
    );
  }
  RAW.push({
    key: `cand-${i}`,
    name,
    kind: KINDS[i % KINDS.length],
    status: 'new',
    score: 0.84 - i * 0.03,
    distress: { tier, oz: i % 3 === 0, qct: i % 4 === 0, poverty: i % 2 === 0 },
    mailing: { addr: `${10 + i} Rural Route`, city: COUNTIES[st][i % 5], state: st, zip: '00000' },
    contact: { name: '', phone: '', email: '', channel: '' },
    contactAttempts: [],
    notes: '',
    parcels,
  });
});

// --- Derive rollups + flatten towers for the map ---
export const KIND_LABEL = {
  individual: 'Individual',
  llc: 'LLC',
  corporation: 'Corporation',
  government: 'Government',
  trust: 'Trust',
};

export const STATUSES = ['new', 'researching', 'contacted', 'interested', 'in_business', 'uninterested'];
export const STATUS_LABEL = {
  new: 'New',
  researching: 'Researching',
  contacted: 'Contacted',
  interested: 'Interested',
  in_business: 'In Business',
  uninterested: 'Uninterested',
};
// Kanban lanes (New excluded — lives in Candidates; Uninterested is the closed lane).
export const KANBAN_LANES = ['researching', 'contacted', 'interested', 'in_business', 'uninterested'];

function derive(o) {
  const states = [...new Set(o.parcels.map((p) => p.state))].sort();
  const towers = o.parcels.flatMap((p) => p.towers);
  const totalAssessed = o.parcels.reduce((s, p) => s + p.assessed, 0);
  return {
    ...o,
    states,
    crossState: states.length > 1,
    towerCount: towers.length,
    activeTowerCount: towers.filter((t) => t.active).length,
    solarCount: o.parcels.reduce((s, p) => s + (p.solar?.length ?? 0), 0),
    parcelCount: o.parcels.length,
    totalAssessed,
    maxHeight: towers.reduce((m, t) => Math.max(m, t.height), 0),
    counties: [...new Set(o.parcels.map((p) => `${p.state}:${p.county}`))],
  };
}

export const LEADS = RAW.map(derive);
export const LEAD_BY_KEY = Object.fromEntries(LEADS.map((l) => [l.key, l]));

// GeoJSON of every tower, tagged with its owner Lead for click→lead routing.
export function towerGeoJSON(leads = LEADS) {
  const features = [];
  for (const l of leads) {
    for (const p of l.parcels) {
      for (const t of p.towers) {
        features.push({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [t.lon, t.lat] },
          properties: {
            ownerKey: l.key,
            ownerName: l.name,
            asr: t.asr,
            height: t.height,
            active: t.active,
            state: p.state,
            status: l.status,
          },
        });
      }
    }
  }
  return { type: 'FeatureCollection', features };
}

export const ALL_STATES = STATES;
export const ALL_COUNTIES = [...new Set(LEADS.flatMap((l) => l.counties))].sort();
export const KIND_VALUES = ['individual', 'llc', 'corporation', 'government', 'trust'];
