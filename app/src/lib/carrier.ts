/**
 * Carriers on a tower — the ULS spectrum licensee(s) identified on an FCC
 * ASR structure (Slice A / #28, consuming the #24 ULS↔ASR join).
 *
 * A CARRIER is the spectrum LICENSEE (AT&T, Verizon, ALLTEL …) — NOT the
 * tower-co / FAA registrant (Crown Castle, American Tower; that's the
 * vendor, Slice B). Each match carries a confidence tag describing how the
 * ULS license was tied to the tower (#24/#11):
 *   verified — exact FCC ASR-number cross-reference (highest confidence)
 *   likely   — a ULS license coordinate within 100 m of the tower
 *   possible — a ULS license coordinate 100–500 m away (lowest confidence)
 *
 * Unmapped carriers arrive with their raw ULS licensee name and must still
 * render — the badge communicates PRESENCE + certainty, not brand recognition.
 *
 * This is the single typed home for the carrier shape + tag metadata, shared
 * by both surfaces (the LeadPage holdings + the schema-driven DetailsPanel)
 * and the tests.
 */

import { WONG } from './palette';

/** The three confidence tiers #24 emits, worst → best is gray → amber → green. */
export type ConfidenceTag = 'verified' | 'likely' | 'possible';

/** Neutral gray for the lowest-confidence + unknown badges (matches palette
 *  NEUTRAL / the `.tag-neutral` chrome). */
const NEUTRAL_GRAY = '#9aa0aa';

/** One ULS licensee identified on a tower. `confidence_tag` is typed loosely
 *  so an unknown tag from a future #24 revision still renders (degraded to a
 *  neutral badge) rather than breaking the list. */
export interface Carrier {
  carrier_name: string;
  callsign: string;
  license_expiry: string | null;
  /** ULS HD status code (A/C/E/T/…) — '' on pre-#216 data (audit M-l). */
  license_status: string;
  /** Human label for the status code ("Active", "Cancelled", …). */
  license_status_desc: string;
  confidence_tag: ConfidenceTag | string;
}

/** ULS HD codes that mean the license no longer authorizes service. A blank /
 *  unknown status is NOT flagged — pre-#216 data carries no status, and a
 *  false "cancelled" would be worse than staying quiet (audit M-l / INH-10). */
const INACTIVE_STATUS_CODES = new Set(['C', 'E', 'T', 'X']);

/** True when the carrier's license is cancelled/expired/terminated — the
 *  badge then marks it so a dead license can't read as a live carrier. */
export function isInactiveLicense(c: Pick<Carrier, 'license_status'>): boolean {
  return INACTIVE_STATUS_CODES.has(c.license_status);
}

/** The word the badge shows for an inactive license — the status label when
 *  the data carries one, else a generic "Inactive". */
export function inactiveLicenseLabel(
  c: Pick<Carrier, 'license_status' | 'license_status_desc'>,
): string {
  return c.license_status_desc.trim() || 'Inactive';
}

/** Display metadata for a confidence tag: the word shown in the badge, the
 *  tone (a CSS class suffix), and the tooltip that tells the co-founder when
 *  to second-guess a match. */
export interface ConfidenceMeta {
  /** The tag word — always present in the badge text so colour is never the
   *  sole signal (WCAG / colourblind-safe). */
  label: string;
  tone: ConfidenceTag | 'unknown';
  /** Wong-palette hue the badge is tinted from (drives the CSS custom props). */
  hue: string;
  tooltip: string;
}

const META: Record<ConfidenceTag, ConfidenceMeta> = {
  verified: {
    label: 'Verified',
    tone: 'verified',
    hue: WONG.bluishGreen,
    tooltip: 'Exact FCC ASR-number cross-reference (highest confidence)',
  },
  likely: {
    label: 'Likely',
    tone: 'likely',
    hue: WONG.orange,
    tooltip: 'ULS license coordinate ≤ 100 m from this tower',
  },
  possible: {
    label: 'Possible',
    tone: 'possible',
    hue: NEUTRAL_GRAY,
    tooltip: 'ULS license coordinate 100–500 m from this tower (lower confidence)',
  },
};

/** Render order for de-duped carriers' confidence — best first. */
export const CONFIDENCE_ORDER: ConfidenceTag[] = ['verified', 'likely', 'possible'];

/** Metadata for a tag, degrading an unrecognised tag to a neutral badge that
 *  still names the raw tag so nothing renders blank. */
export function confidenceMeta(tag: string): ConfidenceMeta {
  const known = META[tag as ConfidenceTag];
  if (known) return known;
  const label = tag ? tag.charAt(0).toUpperCase() + tag.slice(1) : 'Unknown';
  return {
    label,
    tone: 'unknown',
    hue: NEUTRAL_GRAY,
    tooltip: 'Confidence not recorded for this carrier match',
  };
}

/**
 * Parse the `carriers` column into a typed list.
 *
 * The value arrives as a real array from a GeoJSON feature but as a JSON
 * *string* from a DuckDB / parquet row (and over the backend lead API it is
 * already-parsed JSON) — accept all three. A null / blank / malformed value
 * yields `[]` so one bad row never breaks the list. Order is preserved
 * (de-dup already happened upstream in #24); each entry is normalised to the
 * four fields the UI reads.
 */
export function parseCarriers(value: unknown): Carrier[] {
  let arr: unknown = value;
  if (typeof arr === 'string') {
    const s = arr.trim();
    if (s === '') return [];
    try {
      arr = JSON.parse(s);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(arr)) return [];
  return arr
    .filter((x): x is Record<string, unknown> => typeof x === 'object' && x !== null)
    .map((x) => ({
      carrier_name: String(x.carrier_name ?? '').trim(),
      callsign: String(x.callsign ?? '').trim(),
      license_expiry: fmtExpiry(x.license_expiry),
      license_status: String(x.license_status ?? '').trim(),
      license_status_desc: String(x.license_status_desc ?? '').trim(),
      confidence_tag: String(x.confidence_tag ?? '').trim(),
    }));
}

/** Normalise a license-expiry value to a non-empty ISO date string, or null. */
function fmtExpiry(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s === '' ? null : s;
}
