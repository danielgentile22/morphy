// Legacy client-side Lead key: `sha1(normalize_owner_name(name))[:12]` —
// name-ONLY (ADR-061 / ADR-056).
//
// ⚠️ This is NO LONGER the canonical Lead key. ADR-075 (#221) moved the
// authoritative `display_cluster_id` to a name+**state** key (plus a curated
// towerco alias table), computed server-side and baked onto every tower as
// `cid` (national_towers.py) and stamped on the owners index. The map resolves
// a clicked tower via that baked `cid` (see `resolveTowerLeadKey`), and narrows
// towers by the owners-index id set — neither goes through this hash.
//
// What remains here is only the degraded fallback `rowsToFeatureCollection`
// uses when a tower feature has no baked `cid` (a stale towers.json / the
// per-state DuckDB path). Because it is name-only, that fallback can collide
// same-named owners across states and won't match the name+state index — good
// enough to draw a dot, not to open the right Lead. `normalizeOwnerName` stays
// the shared normalizer; do NOT wire `displayClusterId` back into Lead links.

// Suffix / entity noise that doesn't disambiguate owners. Mirrors the Python
// `_NOISE_WORDS`. Run AFTER punctuation is stripped, so the dotted variants
// (L.L.C., INC.) only ever match via their bare forms here — kept verbatim
// for fidelity with the source pattern.
const NOISE_WORDS =
  /\b(LLC|L\.L\.C\.|INC|INC\.|CORP|CORP\.|CO|CO\.|LTD|LTD\.|TRUST|TRUSTEE|TRUSTEES|FAMILY|REVOCABLE|LIVING|ETAL|ET AL|JR|SR|II|III|IV)\b/gi;
// Python's `re` uses Unicode `\w`; mirror it with \p{L}\p{N}_ (the `u` flag)
// so an accented letter is kept, not stripped, exactly as upstream.
const PUNCT = /[^\p{L}\p{N}_\s]/gu;
const MULTI_WS = /\s+/gu;
// U.S.-federal aliases all collapse to one key (matched against the fully
// normalized, single-spaced string).
const US_GOV_ALIAS = /^(?:(?:U\s*S\s*A?\s*)+|UNITED STATES(?:\s+OF\s+AMERICA)?)$/;

/** Uppercased, punctuation-stripped, noise-stripped, sorted-token owner key.
 *  Parity port of `scripts/preprocess/cluster.normalize_owner_name`. */
export function normalizeOwnerName(name: string | null | undefined): string {
  if (name == null) return '';
  let s = String(name).toUpperCase();
  s = s.replace(PUNCT, ' ');
  s = s.replace(NOISE_WORDS, ' ');
  s = s.replace(MULTI_WS, ' ').trim();
  if (!s) return '';
  if (US_GOV_ALIAS.test(s)) return 'UNITED STATES';
  return s.split(' ').sort().join(' ');
}

/** Stable Lead key: first 12 hex of sha1(normalized name). Empty for an
 *  un-clusterable (blank) name — the caller treats that as "no Lead". */
export function displayClusterId(ownerNameNorm: string): string {
  if (!ownerNameNorm) return '';
  return sha1Hex(ownerNameNorm).slice(0, 12);
}

/** Owner name (raw, e.g. a tower's `parcel_owner`) → Lead key, in one step. */
export function ownerNameToClusterId(name: string | null | undefined): string {
  return displayClusterId(normalizeOwnerName(name));
}

// ── SHA-1 ────────────────────────────────────────────────────────────────
// A small, dependency-free SHA-1 over the UTF-8 bytes of a string. Kept
// synchronous (vs the async Web Crypto `subtle.digest`) so `displayClusterId`
// is a pure function — easy to unit-test and to call inline on a map click.

function sha1Hex(str: string): string {
  const bytes = utf8Bytes(str);
  const ml = bytes.length * 8; // message length in bits

  // Padding: 0x80, then zeros, to 56 mod 64; then 64-bit big-endian length.
  const withOne = bytes.length + 1;
  const total = withOne + ((56 - (withOne % 64) + 64) % 64) + 8;
  const msg = new Uint8Array(total);
  msg.set(bytes);
  msg[bytes.length] = 0x80;
  // 64-bit length, big-endian. ml < 2^32 in practice (short owner names),
  // so the high word is 0 and the low word carries the bit length.
  const dv = new DataView(msg.buffer);
  dv.setUint32(total - 4, ml >>> 0, false);
  dv.setUint32(total - 8, Math.floor(ml / 0x100000000), false);

  let h0 = 0x67452301;
  let h1 = 0xefcdab89;
  let h2 = 0x98badcfe;
  let h3 = 0x10325476;
  let h4 = 0xc3d2e1f0;

  const w = new Int32Array(80);
  for (let off = 0; off < total; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getInt32(off + i * 4, false);
    for (let i = 16; i < 80; i++) {
      w[i] = rotl(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    }
    let a = h0;
    let b = h1;
    let c = h2;
    let d = h3;
    let e = h4;
    for (let i = 0; i < 80; i++) {
      let f: number;
      let k: number;
      if (i < 20) {
        f = (b & c) | (~b & d);
        k = 0x5a827999;
      } else if (i < 40) {
        f = b ^ c ^ d;
        k = 0x6ed9eba1;
      } else if (i < 60) {
        f = (b & c) | (b & d) | (c & d);
        k = 0x8f1bbcdc;
      } else {
        f = b ^ c ^ d;
        k = 0xca62c1d6;
      }
      const tmp = (rotl(a, 5) + f + e + k + w[i]) | 0;
      e = d;
      d = c;
      c = rotl(b, 30);
      b = a;
      a = tmp;
    }
    h0 = (h0 + a) | 0;
    h1 = (h1 + b) | 0;
    h2 = (h2 + c) | 0;
    h3 = (h3 + d) | 0;
    h4 = (h4 + e) | 0;
  }
  return [h0, h1, h2, h3, h4].map(hex32).join('');
}

function rotl(n: number, bits: number): number {
  return (n << bits) | (n >>> (32 - bits));
}
function hex32(n: number): string {
  return (n >>> 0).toString(16).padStart(8, '0');
}
function utf8Bytes(str: string): Uint8Array {
  if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(str);
  // jsdom/node always have TextEncoder; this is a defensive fallback.
  const out: number[] = [];
  for (const ch of str) {
    let cp = ch.codePointAt(0) ?? 0;
    if (cp < 0x80) out.push(cp);
    else if (cp < 0x800) out.push(0xc0 | (cp >> 6), 0x80 | (cp & 0x3f));
    else if (cp < 0x10000)
      out.push(0xe0 | (cp >> 12), 0x80 | ((cp >> 6) & 0x3f), 0x80 | (cp & 0x3f));
    else
      out.push(
        0xf0 | (cp >> 18),
        0x80 | ((cp >> 12) & 0x3f),
        0x80 | ((cp >> 6) & 0x3f),
        0x80 | (cp & 0x3f),
      );
  }
  return new Uint8Array(out);
}
