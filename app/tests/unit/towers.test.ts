import { describe, it, expect } from 'vitest';
import {
  rowsToFeatureCollection,
  filterTowers,
  heightFeet,
  towerOwnerLabel,
  towerHoverHtml,
  type TowerProps,
} from '../../src/lib/towers';
import type { TowerRow } from '../../src/lib/duckdb';
import { ownerNameToClusterId } from '../../src/lib/owner-cluster';

function row(over: Partial<TowerRow> = {}): TowerRow {
  return {
    asr: '080946',
    owner: 'MITCHELL VICKI',
    height_m: 79.248,
    state: 'AR',
    active: true,
    lat: 33.0,
    lon: -91.3,
    ...over,
  };
}

describe('rowsToFeatureCollection', () => {
  it('maps a row to a GeoJSON Point with [lon, lat] and flat props', () => {
    const fc = rowsToFeatureCollection([row()]);
    expect(fc.type).toBe('FeatureCollection');
    expect(fc.features).toHaveLength(1);
    const f = fc.features[0];
    expect(f.geometry).toEqual({ type: 'Point', coordinates: [-91.3, 33.0] });
    expect(f.properties).toEqual({
      asr: '080946',
      owner: 'MITCHELL VICKI',
      cid: ownerNameToClusterId('MITCHELL VICKI'),
      height_m: 79.248,
      state: 'AR',
      active: true,
      date_built: null,
      tower_owner: null,
      tower_owner_street: null,
      tower_owner_city: null,
      tower_owner_state: null,
      tower_owner_zip: null,
      tower_owner_phone: null,
    });
  });

  it('carries the build date + ASR owner contact block, blank → null (M-b/M-c)', () => {
    const fc = rowsToFeatureCollection([
      row({
        date_built: '1990-06-14',
        tower_owner: 'SBA TOWERS II LLC',
        tower_owner_street: '8051 CONGRESS AVE',
        tower_owner_city: 'BOCA RATON',
        tower_owner_state: 'FL',
        tower_owner_zip: '33487',
        tower_owner_phone: '(561) 995-7670',
      }),
      row({ asr: 'faa', date_built: '', tower_owner: '  ' }), // FAA-style blanks
    ]);
    const p = fc.features[0].properties;
    expect(p.date_built).toBe('1990-06-14');
    expect(p.tower_owner).toBe('SBA TOWERS II LLC');
    expect(p.tower_owner_street).toBe('8051 CONGRESS AVE');
    expect(p.tower_owner_phone).toBe('(561) 995-7670');
    const faa = fc.features[1].properties;
    expect(faa.date_built).toBeNull(); // blank string normalized to null
    expect(faa.tower_owner).toBeNull();
  });

  it('bakes the owner cluster id onto each tower for filter joins', () => {
    const fc = rowsToFeatureCollection([row(), row({ owner: '' })]);
    expect(fc.features[0].properties.cid).toBe('209af3ad593f'); // MITCHELL VICKI
    expect(fc.features[1].properties.cid).toBe(''); // un-clusterable owner
  });

  it('drops rows without finite coordinates', () => {
    const fc = rowsToFeatureCollection([
      row({ lat: Number.NaN }),
      row({ lon: undefined as unknown as number }),
      row({ asr: 'keep' }),
    ]);
    expect(fc.features).toHaveLength(1);
    expect(fc.features[0].properties.asr).toBe('keep');
  });

  it('normalizes a missing / null landowner to a blank string', () => {
    const fc = rowsToFeatureCollection([row({ owner: null })]);
    expect(fc.features[0].properties.owner).toBe('');
  });

  it('coerces a non-true active flag to false', () => {
    const fc = rowsToFeatureCollection([row({ active: null })]);
    expect(fc.features[0].properties.active).toBe(false);
  });
});

describe('filterTowers', () => {
  const fc = rowsToFeatureCollection([
    row({ asr: 'a', owner: 'MITCHELL VICKI' }),
    row({ asr: 'b', owner: 'WEYERHAEUSER COMPANY' }),
    row({ asr: 'c', owner: 'MITCHELL VICKI' }),
  ]);

  it('returns the collection unchanged when no filter is active (null)', () => {
    expect(filterTowers(fc, null)).toBe(fc);
  });

  it('keeps only towers whose owner cluster id is in the set', () => {
    const keep = new Set([ownerNameToClusterId('MITCHELL VICKI')]);
    const out = filterTowers(fc, keep);
    expect(out.features.map((f) => f.properties.asr)).toEqual(['a', 'c']);
  });

  it('an empty set drops every tower', () => {
    expect(filterTowers(fc, new Set()).features).toHaveLength(0);
  });

  // Archived antennas (UI overhaul round 2) drop out of the map unless shown.
  it('hides archived towers by ASR when not showing archived', () => {
    const out = filterTowers(fc, null, { asrs: new Set(['b']), show: false });
    expect(out.features.map((f) => f.properties.asr)).toEqual(['a', 'c']);
  });

  it('keeps archived towers when show is true', () => {
    const out = filterTowers(fc, null, { asrs: new Set(['b']), show: true });
    expect(out.features.map((f) => f.properties.asr)).toEqual(['a', 'b', 'c']);
  });

  it('applies archive narrowing alongside the owner-cluster set', () => {
    const keep = new Set([ownerNameToClusterId('MITCHELL VICKI')]); // a + c
    const out = filterTowers(fc, keep, { asrs: new Set(['c']), show: false });
    expect(out.features.map((f) => f.properties.asr)).toEqual(['a']); // c archived out
  });

  it('returns the collection unchanged when nothing narrows it', () => {
    expect(filterTowers(fc, null, { asrs: new Set(), show: false })).toBe(fc);
    expect(filterTowers(fc, null, { asrs: new Set(['b']), show: true })).toBe(fc);
  });
});

describe('heightFeet', () => {
  it('converts metres to whole feet', () => {
    expect(heightFeet(79.248)).toBe(260);
    expect(heightFeet(0)).toBe(0);
  });
  it('returns null for missing / non-finite heights', () => {
    expect(heightFeet(null)).toBeNull();
    expect(heightFeet(undefined)).toBeNull();
    expect(heightFeet(Number.NaN)).toBeNull();
  });
});

describe('towerOwnerLabel', () => {
  it('passes through a real owner', () => {
    expect(towerOwnerLabel('WEYERHAEUSER COMPANY')).toBe('WEYERHAEUSER COMPANY');
  });
  it('stands in for a blank / missing owner', () => {
    expect(towerOwnerLabel('')).toBe('Unknown landowner');
    expect(towerOwnerLabel('   ')).toBe('Unknown landowner');
    expect(towerOwnerLabel(null)).toBe('Unknown landowner');
  });
});

describe('towerHoverHtml', () => {
  const props: TowerProps = {
    asr: '080946',
    owner: 'MITCHELL VICKI',
    cid: '209af3ad593f',
    height_m: 79.248,
    state: 'AR',
    active: true,
    date_built: null,
    tower_owner: null,
    tower_owner_street: null,
    tower_owner_city: null,
    tower_owner_state: null,
    tower_owner_zip: null,
    tower_owner_phone: null,
  };
  it('previews owner, ASR, height (ft) and state', () => {
    const html = towerHoverHtml(props);
    expect(html).toContain('MITCHELL VICKI');
    expect(html).toContain('ASR 080946');
    expect(html).toContain('260 ft');
    expect(html).toContain('AR');
  });
  it('omits height when unknown', () => {
    const html = towerHoverHtml({ ...props, height_m: null });
    expect(html).not.toContain('ft');
    expect(html).toContain('ASR 080946');
  });
  it('escapes owner names so HTML cannot inject', () => {
    const html = towerHoverHtml({ ...props, owner: 'A & B <Co>' });
    expect(html).toContain('A &amp; B &lt;Co&gt;');
    expect(html).not.toContain('<Co>');
  });
});
