import { describe, it, expect } from 'vitest';
import {
  rowsToFeatureCollection,
  filterTowers,
  heightFeet,
  towerOwnerLabel,
  resolveTowerLeadKey,
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
    });
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

describe('resolveTowerLeadKey', () => {
  it('resolves a tower owner to the same Lead key as the owners index', () => {
    expect(resolveTowerLeadKey({ owner: 'MITCHELL VICKI' })).toBe(
      ownerNameToClusterId('MITCHELL VICKI'),
    );
    expect(resolveTowerLeadKey({ owner: 'MITCHELL VICKI' })).toBe('209af3ad593f');
  });
  it('is empty when the landowner is un-clusterable (no Lead to open)', () => {
    expect(resolveTowerLeadKey({ owner: '' })).toBe('');
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
