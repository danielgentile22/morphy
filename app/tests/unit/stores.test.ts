import { describe, it, expect } from 'vitest';
import { parseCompositeIndex } from '../../src/lib/catalog';
import { AppStore } from '../../src/lib/stores.svelte';

const INDEX = parseCompositeIndex({
  schema_version: 1,
  generated_at: '',
  states: [
    { fips: '05', abbr: 'AR', name: 'Arkansas', bbox: [-94.6, 33, -89.6, 36.5], counts: { solar_facility: 208 } },
    { fips: '30', abbr: 'MT', name: 'Montana', bbox: [-116, 44.3, -104, 49], counts: { solar_facility: 92 } },
  ],
});

describe('AppStore mutations', () => {
  it('sets and clears the selection', () => {
    const s = new AppStore();
    expect(s.selection).toBeNull();
    s.setSelection({ kind: 'parcel', props: { owner_name: 'X' } });
    expect(s.selection?.kind).toBe('parcel');
    s.clearSelection();
    expect(s.selection).toBeNull();
  });

  it('toggles and reads layer visibility', () => {
    const s = new AppStore();
    expect(s.isLayerVisible('towers')).toBe(false);
    s.setLayerVisible('towers', true);
    expect(s.isLayerVisible('towers')).toBe(true);
    s.toggleLayer('towers');
    expect(s.isLayerVisible('towers')).toBe(false);
  });

  it('dismisses a notice', () => {
    const s = new AppStore();
    s.notice = 'heads up';
    s.dismissNotice();
    expect(s.notice).toBeNull();
  });

  it('records a one-shot fly target (ASR search)', () => {
    const s = new AppStore();
    expect(s.flyTarget).toBeNull();
    s.flyTo([-91, 34], 13);
    expect(s.flyTarget).toEqual({ center: [-91, 34], zoom: 13 });
  });
});

describe('AppStore all-states derivations (#119)', () => {
  it('frames to the union of every anchor bbox (no active state)', () => {
    const s = new AppStore();
    expect(s.anchorBounds).toBeNull();
    s.index = INDEX;
    expect(s.anchorBounds).toEqual([
      [-116, 33],
      [-89.6, 49],
    ]);
  });

  it('sums the static Solar total across every anchor state', () => {
    const s = new AppStore();
    expect(s.solarCount).toBe(0);
    s.index = INDEX;
    expect(s.solarCount).toBe(300); // 208 (AR) + 92 (MT)
  });

  it('starts with no parcel sources until they are probed', () => {
    expect(new AppStore().parcelSources).toEqual([]);
  });
});
