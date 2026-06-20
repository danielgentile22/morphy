import { describe, it, expect } from 'vitest';
import type { AuditIndex, Signal } from '../../src/lib/audit-data';
import type { CatalogConfig } from '../../src/lib/catalog-config';
import { buildCatalog, type CatalogModel } from '../../src/lib/catalog';

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
