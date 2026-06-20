import { describe, it, expect } from 'vitest';
import type { AuditIndex, Signal } from '../../src/lib/audit-data';
import type { CatalogConfig } from '../../src/lib/catalog-config';
import {
  buildCatalog,
  dossierTarget,
  stateStrip,
  type CatalogModel,
  type DataPoint,
} from '../../src/lib/catalog';

function sig(id: string, confidence: string, extra: Partial<Signal> = {}): Signal {
  return {
    id,
    card: extra.card ?? 'T-XX',
    surface: extra.surface ?? 'surface',
    priority: extra.priority ?? 'P1',
    tags: {
      upstream_origin: 'official_filing',
      freshness_risk: 'low',
      derivation_risk: 'low',
      verifiability: 'per_instance_checkable',
      confidence: confidence as Signal['tags']['confidence'],
      ...extra.tags,
    },
    verdict: extra.verdict ?? `verdict for ${id}`,
    dossier: extra.dossier ?? `doc.md#${id}`,
  };
}

function idx(signals: Signal[]): AuditIndex {
  return { signals } as AuditIndex;
}

// A stub config so the builder's behaviour is asserted independently of the real
// curated groupings (those are checked once, separately, below).
const STUB: CatalogConfig = {
  groups: [
    { id: 'g1', emoji: '', title: 'G1', blurb: '', order: 1 },
    { id: 'g2', emoji: '', title: 'G2', blurb: '', order: 2 },
  ],
  newlyAdded: { id: 'newly', emoji: '', title: 'Newly', blurb: '', order: -1 },
  entries: {
    alpha: { group: 'g1', meaning: 'Alpha.' },
    beta: { group: 'g1', meaning: 'Beta.' },
    owner_name: { group: 'g1', meaning: 'The deed owner.' },
    gamma: { group: 'g2', meaning: 'Gamma.' },
    delta: { group: 'g2', meaning: 'Delta.' },
    epsilon: { group: 'g2', meaning: 'Epsilon.' },
    zeta: { group: 'g2', meaning: 'Zeta.' },
  },
};

// owner_name is per-state (one state weakest); g2 is mostly high with one low.
const SIGNALS: Signal[] = [
  sig('owner_name@05', 'high'),
  sig('owner_name@12', 'high'),
  sig('owner_name@30', 'high'),
  sig('owner_name@54', 'low'),
  sig('alpha', 'high'),
  sig('beta', 'medium'),
  sig('gamma', 'high'),
  sig('delta', 'high'),
  sig('epsilon', 'high'),
  sig('zeta', 'low'),
  sig('orphan', 'medium'), // absent from STUB.entries → Newly added
];

function group(model: CatalogModel, id: string) {
  const g = model.groups.find((x) => x.def.id === id);
  if (!g) throw new Error(`no group ${id}`);
  return g;
}

describe('buildCatalog — per-state collapse', () => {
  const model = buildCatalog(idx(SIGNALS), STUB);

  it('collapses the four per-state variants into one logical row', () => {
    const ownerRows = group(model, 'g1').points.filter((p) => p.baseId === 'owner_name');
    expect(ownerRows).toHaveLength(1);
    const owner = ownerRows[0];
    expect(owner.isPerState).toBe(true);
    expect(owner.states.map((c) => c.fips)).toEqual(['05', '12', '30', '54']);
    expect(owner.states.map((c) => c.confidence)).toEqual(['high', 'high', 'high', 'low']);
  });

  it('uses the weakest state as the row-level representative', () => {
    const owner = group(model, 'g1').points.find((p) => p.baseId === 'owner_name')!;
    expect(owner.confidence).toBe('low'); // @54 is the weakest of the four
    expect(owner.verdict).toBe('verdict for owner_name@54');
  });

  it('keeps a national signal single, with no state cells', () => {
    const alpha = group(model, 'g1').points.find((p) => p.baseId === 'alpha')!;
    expect(alpha.isPerState).toBe(false);
    expect(alpha.states).toEqual([]);
  });
});

describe('buildCatalog — group assignment + newly-added fallback', () => {
  const model = buildCatalog(idx(SIGNALS), STUB);

  it('assigns each recognised point to its configured group', () => {
    expect(group(model, 'g1').points.map((p) => p.baseId)).toContain('alpha');
    expect(group(model, 'g2').points.map((p) => p.baseId)).toContain('gamma');
  });

  it('routes an unrecognised base id to Newly added and never drops it', () => {
    const newly = group(model, 'newly');
    const orphan = newly.points.find((p) => p.baseId === 'orphan')!;
    expect(orphan).toBeDefined();
    expect(orphan.recognised).toBe(false);
    expect(orphan.meaning).toBeNull();
    expect(orphan.verdict).toBe('verdict for orphan'); // raw verdict carried through
  });

  it('drops empty groups (no empty rows)', () => {
    // STUB has g1/g2/newly all populated; an unused group id must not appear.
    const sparse = buildCatalog(idx([sig('alpha', 'high')]), STUB);
    expect(sparse.groups.map((g) => g.def.id)).toEqual(['g1']);
  });
});

describe('buildCatalog — group rollups', () => {
  const model = buildCatalog(idx(SIGNALS), STUB);

  it('headline trust is most-common, breaking ties to the lower trust', () => {
    // g1: {low, medium, high} all tie at 1 → conservative pick is low.
    expect(group(model, 'g1').headlineTrust).toBe('low');
    // g2: high×3 vs low×1 → most-common is high.
    expect(group(model, 'g2').headlineTrust).toBe('high');
  });

  it('biggest caveat is the lowest-confidence point’s verdict', () => {
    expect(group(model, 'g1').biggestCaveat).toBe('verdict for owner_name@54');
    expect(group(model, 'g2').biggestCaveat).toBe('verdict for zeta');
  });

  it('counts trust levels per group', () => {
    expect(group(model, 'g1').counts).toEqual({ low: 1, medium: 1, high: 1 });
    expect(group(model, 'g2').counts).toEqual({ low: 1, high: 3 });
  });
});

describe('buildCatalog — deterministic ordering', () => {
  const model = buildCatalog(idx(SIGNALS), STUB);

  it('orders groups Newly-added first, then configured order', () => {
    expect(model.groups.map((g) => g.def.id)).toEqual(['newly', 'g1', 'g2']);
  });

  it('orders points within a group weakest-trust-first (base-id tie-break)', () => {
    expect(group(model, 'g1').points.map((p) => p.baseId)).toEqual(['owner_name', 'beta', 'alpha']);
    expect(group(model, 'g2').points.map((p) => p.baseId)).toEqual(['zeta', 'delta', 'epsilon', 'gamma']);
  });
});

describe('stateStrip — per-state trust strip', () => {
  const model = buildCatalog(idx(SIGNALS), STUB);
  const pointOf = (baseId: string): DataPoint =>
    model.groups.flatMap((g) => g.points).find((p) => p.baseId === baseId)!;

  it('projects the four per-state cells onto a fixed AR/FL/MT/WV grid', () => {
    const strip = stateStrip(pointOf('owner_name'));
    expect(strip.map((c) => c.fips)).toEqual(['05', '12', '30', '54']);
    expect(strip.map((c) => c.abbr)).toEqual(['AR', 'FL', 'MT', 'WV']);
    // Trust per cell comes straight from the underlying signal (auto-populate).
    expect(strip.map((c) => c.cell?.confidence)).toEqual(['high', 'high', 'high', 'low']);
  });

  it('links each cell at the underlying per-state signal id', () => {
    const strip = stateStrip(pointOf('owner_name'));
    expect(strip.map((c) => c.cell?.signal.id)).toEqual([
      'owner_name@05',
      'owner_name@12',
      'owner_name@30',
      'owner_name@54',
    ]);
  });

  it('returns no strip for a national (non-per-state) point', () => {
    expect(stateStrip(pointOf('alpha'))).toEqual([]);
  });

  it('shows an honest empty cell when a state is missing the field', () => {
    // Only three of the four states carry owner_name → WV (54) has no signal.
    const partial = buildCatalog(
      idx([sig('owner_name@05', 'high'), sig('owner_name@12', 'medium'), sig('owner_name@30', 'high')]),
      STUB,
    );
    const point = partial.groups.flatMap((g) => g.points).find((p) => p.baseId === 'owner_name')!;
    const strip = stateStrip(point);
    expect(strip.map((c) => c.fips)).toEqual(['05', '12', '30', '54']); // still 4 columns
    expect(strip[3].cell).toBeNull(); // WV is an honest gap, not dropped
    expect(strip.slice(0, 3).every((c) => c.cell !== null)).toBe(true);
  });
});

describe('dossierTarget — "Why this rating" deep-link', () => {
  const pointOf = (signals: Signal[], baseId: string): DataPoint =>
    buildCatalog(idx(signals), STUB)
      .groups.flatMap((g) => g.points)
      .find((p) => p.baseId === baseId)!;

  it('splits a national point’s `file.md#anchor` dossier ref', () => {
    const point = pointOf([sig('tower_coords', 'high', { dossier: 'fcc-asr.md#tower_coords' })], 'tower_coords');
    expect(dossierTarget(point)).toEqual({ file: 'fcc-asr.md', anchor: 'tower_coords' });
  });

  it('resolves a per-state field to its WEAKEST state’s dossier section', () => {
    // @54 (WV) is the lowest-trust variant → the representative → its dossier.
    const point = pointOf(
      [
        sig('owner_name@05', 'high', { dossier: 'parcels-AR.md#owner_name' }),
        sig('owner_name@12', 'high', { dossier: 'parcels-FL.md#owner_name' }),
        sig('owner_name@30', 'high', { dossier: 'parcels-MT.md#owner_name' }),
        sig('owner_name@54', 'low', { dossier: 'parcels-WV.md#owner_name' }),
      ],
      'owner_name',
    );
    // Anchor keys the `## Signal: \`owner_name\`` heading on the BASE id, not @54.
    expect(dossierTarget(point)).toEqual({ file: 'parcels-WV.md', anchor: 'owner_name' });
  });

  it('falls back to the base id when the dossier ref carries no anchor', () => {
    const point = pointOf([sig('alpha', 'high', { dossier: 'doc.md' })], 'alpha');
    expect(dossierTarget(point)).toEqual({ file: 'doc.md', anchor: 'alpha' });
  });
});

describe('buildCatalog — default config grouping calls', () => {
  it('routes owner_name→Landowner, situs_address→Land, interestingness_score→Derived', () => {
    const model = buildCatalog(
      idx([sig('owner_name@05', 'high'), sig('situs_address@05', 'high'), sig('interestingness_score', 'medium')]),
    );
    const groupOf = (baseId: string) =>
      model.groups.find((g) => g.points.some((p) => p.baseId === baseId))?.def.id;
    expect(groupOf('owner_name')).toBe('landowner');
    expect(groupOf('situs_address')).toBe('land');
    expect(groupOf('interestingness_score')).toBe('derived');
  });
});
