import { describe, it, expect } from 'vitest';
import { errMsg, parcelSources, unionBounds } from '../../src/lib/stores-helpers';
import { pmtilesUrl } from '../../src/lib/data';

describe('parcelSources', () => {
  // All-states map (UI overhaul #119): parcels render per anchor state, so the
  // map adds one vector source for each state whose parcels.pmtiles is present.
  const states = [{ fips: '05' }, { fips: '12' }, { fips: '30' }, { fips: '54' }];

  it('returns a source per present-probe state, in input order', () => {
    const got = parcelSources(states, {
      '05': 'present',
      '12': 'present',
      '30': 'present',
      '54': 'present',
    });
    expect(got).toEqual([
      { state: '05', tilesUrl: pmtilesUrl('05') },
      { state: '12', tilesUrl: pmtilesUrl('12') },
      { state: '30', tilesUrl: pmtilesUrl('30') },
      { state: '54', tilesUrl: pmtilesUrl('54') },
    ]);
  });

  it('pins the per-state tiles URL to the composite convention', () => {
    expect(parcelSources([{ fips: '05' }], { '05': 'present' })).toEqual([
      { state: '05', tilesUrl: '/data/processed/composite/05/parcels.pmtiles' },
    ]);
  });

  it('skips absent and unreachable probes (degrade to fewer parcel sources)', () => {
    const got = parcelSources(states, {
      '05': 'present',
      '12': 'absent',
      '30': 'unreachable',
      '54': 'present',
    });
    expect(got.map((s) => s.state)).toEqual(['05', '54']);
  });

  it('drops a state with no probe entry', () => {
    expect(parcelSources(states, { '05': 'present' }).map((s) => s.state)).toEqual(['05']);
  });

  it('is empty when nothing probes present', () => {
    expect(parcelSources(states, { '05': 'absent', '12': 'unreachable' })).toEqual([]);
    expect(parcelSources([], {})).toEqual([]);
  });
});

describe('unionBounds', () => {
  it('unions state bboxes into [[w, s], [e, n]] fit corners', () => {
    // AR + MT — the union should span the westmost/southmost to eastmost/northmost.
    expect(
      unionBounds([
        { bbox: [-94.62, 33.0, -89.64, 36.5] },
        { bbox: [-116.06, 44.36, -104.04, 49.0] },
      ]),
    ).toEqual([
      [-116.06, 33.0],
      [-89.64, 49.0],
    ]);
  });
  it('returns the single bbox corners for one state', () => {
    expect(unionBounds([{ bbox: [-94.62, 33.0, -89.64, 36.5] }])).toEqual([
      [-94.62, 33.0],
      [-89.64, 36.5],
    ]);
  });
  it('is null when there are no states', () => {
    expect(unionBounds([])).toBeNull();
  });
});

describe('errMsg', () => {
  it('uses the Error message for Error instances', () => {
    expect(errMsg(new Error('boom'))).toBe('boom');
  });
  it('coerces non-Error throws', () => {
    expect(errMsg('lit')).toBe('lit');
    expect(errMsg(404)).toBe('404');
  });
});
