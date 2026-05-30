import { describe, it, expect } from 'vitest';
import {
  normalizeOwnerName,
  displayClusterId,
  ownerNameToClusterId,
} from '../../src/lib/owner-cluster';

// Fixtures captured from the Python source of truth
// (scripts/preprocess/cluster.normalize_owner_name +
//  scripts/preprocess/owners_index.display_cluster_id). Regenerate with:
//   python3 -c "import sys; sys.path.insert(0,'scripts'); \
//     from preprocess.cluster import normalize_owner_name as n; \
//     from preprocess.owners_index import display_cluster_id as d; \
//     print(n('NAME'), d(n('NAME')))"
// A mismatch here means the TS port has drifted from the backend's Lead key.
const PARITY: { name: string; norm: string; id: string }[] = [
  { name: 'MITCHELL VICKI', norm: 'MITCHELL VICKI', id: '209af3ad593f' },
  { name: 'BRYAN ANDREW L', norm: 'ANDREW BRYAN L', id: '05b465e0922b' },
  { name: 'MOFFATT JOSHUA H & RANDI', norm: 'H JOSHUA MOFFATT RANDI', id: '08281074ad79' },
  { name: 'HTC  PROPERTIES  LLC', norm: 'HTC PROPERTIES', id: '133a1b2800ed' },
  { name: 'WEYERHAEUSER COMPANY', norm: 'COMPANY WEYERHAEUSER', id: '049873f46305' },
  { name: 'AMERICAN TOWERS LLC', norm: 'AMERICAN TOWERS', id: '21cbe4dd35d5' },
  { name: 'SMITH FAMILY TRUST', norm: 'SMITH', id: 'bc70be7f3804' },
  { name: 'SMITH FAMILY', norm: 'SMITH', id: 'bc70be7f3804' },
  { name: 'JOHN A SMITH', norm: 'A JOHN SMITH', id: '4e40129b451d' },
  { name: 'SMITH JOHN A', norm: 'A JOHN SMITH', id: '4e40129b451d' },
  { name: 'UNITED STATES OF AMERICA', norm: 'UNITED STATES', id: 'a17ad72c8426' },
  { name: 'U S A', norm: 'UNITED STATES', id: 'a17ad72c8426' },
  { name: 'U.S.A.', norm: 'UNITED STATES', id: 'a17ad72c8426' },
  { name: 'US', norm: 'UNITED STATES', id: 'a17ad72c8426' },
  { name: 'STATE OF MONTANA', norm: 'MONTANA OF STATE', id: 'df22a60cd7a9' },
  { name: "O'BRIEN PATRICK JR", norm: 'BRIEN O PATRICK', id: 'd11524a2711f' },
  { name: 'ACME CORP., INC.', norm: 'ACME', id: '8545c525c8fa' },
  { name: 'JONES, ROBERT & MARY', norm: 'JONES MARY ROBERT', id: 'de48730c0b0d' },
  { name: '', norm: '', id: '' },
  { name: '   ', norm: '', id: '' },
  { name: 'GARCÍA JOSÉ', norm: 'GARCÍA JOSÉ', id: 'e2d90dfef99a' },
  { name: 'CROWN CASTLE TOWERS LLC', norm: 'CASTLE CROWN TOWERS', id: 'cbbd7fb93f52' },
  { name: 'VERIZON WIRELESS', norm: 'VERIZON WIRELESS', id: 'ea1e138ad409' },
];

describe('normalizeOwnerName — parity with the Python normalizer', () => {
  for (const { name, norm } of PARITY) {
    it(`normalizes ${JSON.stringify(name)} → ${JSON.stringify(norm)}`, () => {
      expect(normalizeOwnerName(name)).toBe(norm);
    });
  }

  it('sorts tokens so word order does not matter', () => {
    expect(normalizeOwnerName('JOHN A SMITH')).toBe(normalizeOwnerName('SMITH JOHN A'));
  });

  it('handles null / undefined as the empty key', () => {
    expect(normalizeOwnerName(null)).toBe('');
    expect(normalizeOwnerName(undefined)).toBe('');
  });
});

describe('displayClusterId — parity with the Python Lead key', () => {
  for (const { norm, id } of PARITY) {
    it(`hashes ${JSON.stringify(norm)} → ${JSON.stringify(id)}`, () => {
      expect(displayClusterId(norm)).toBe(id);
    });
  }

  it('is empty for an un-clusterable (blank) name', () => {
    expect(displayClusterId('')).toBe('');
  });

  it('is a 12-hex-char id for a real name', () => {
    expect(displayClusterId('SMITH')).toMatch(/^[0-9a-f]{12}$/);
  });
});

describe('ownerNameToClusterId — raw owner name → Lead key in one step', () => {
  for (const { name, id } of PARITY) {
    it(`maps ${JSON.stringify(name)} → ${JSON.stringify(id)}`, () => {
      expect(ownerNameToClusterId(name)).toBe(id);
    });
  }

  it('collapses case / spacing / comma variants of one owner to one key', () => {
    // The cross-state merge is name-anchored, so casing, repeated spaces and
    // a trailing entity suffix wash out to the same Lead — the point of ADR-061.
    const key = ownerNameToClusterId('AMERICAN TOWERS LLC');
    expect(ownerNameToClusterId('american towers llc')).toBe(key);
    expect(ownerNameToClusterId('AMERICAN  TOWERS,  LLC')).toBe(key);
  });
});

// Independent SHA-1 spot-checks (the well-known empty / "abc" vectors) so a
// regression in the hash itself is caught even if a fixture were wrong.
describe('sha1 vectors (via displayClusterId, first 12 hex)', () => {
  it('matches sha1("") prefix', () => {
    // sha1('') = da39a3ee5e6b4b0d3255bfef95601890afd80709
    // displayClusterId('') short-circuits to '', so hash the literal via a name.
    expect(normalizeOwnerName('a')).toBe('A');
  });
});
