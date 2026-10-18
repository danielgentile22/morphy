// Tiny display helpers for the Lead surfaces.

import type { LeadStatus } from './lead-status';

export function money(n: number): string {
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${Math.round(n / 1e3)}K`;
  return `$${Math.round(n)}`;
}

/** Metres → whole feet (tower heights are stored in metres; the team
 *  thinks in feet). Returns '—' for a missing height. */
export function feet(metres: number | null | undefined): string {
  if (metres == null) return '—';
  return `${Math.round(metres * 3.28084)} ft`;
}

/** A channel/best-channel value for display ('' → '—'). */
export function channelLabel(channel: string): string {
  return channel || '—';
}

export const KIND_LABELS: Record<string, string> = {
  individual: 'Individual',
  llc: 'LLC',
  corporation: 'Corporation',
  partnership: 'Partnership',
  trust: 'Trust',
  gov: 'Government',
  church: 'Church',
  school: 'School',
  unknown: 'Unknown',
};

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}

export function statusVar(status: LeadStatus | string): string {
  return `var(--s-${status})`;
}

/** A non-color cue per status (PRD #121): a distinct glyph so meaning never
 *  rides on hue alone. Shown only in colorblind mode (gated by the `.cb-cue`
 *  CSS class). The won/lost pair is the deliberate ✓ / ✗ contrast. */
const STATUS_GLYPHS: Record<string, string> = {
  new: '○',
  researching: '◔',
  contacted: '◑',
  interested: '☆',
  in_business: '✓',
  uninterested: '✗',
};

export function statusGlyph(status: LeadStatus | string): string {
  return STATUS_GLYPHS[status] ?? '•';
}

/** Distress summary string, e.g. "distressed · OZ QCT". */
export function distressText(d: {
  distress_tier: string;
  in_oz: boolean;
  in_qct: boolean;
  persistent_poverty: boolean;
}): string {
  const flags = [d.in_oz && 'OZ', d.in_qct && 'QCT', d.persistent_poverty && 'PP']
    .filter(Boolean)
    .join(' ');
  const tier = d.distress_tier || 'none';
  return flags ? `${tier} · ${flags}` : tier;
}

/** One-line mailing address. Some state sources pack city, state and ZIP
 *  into `addr` as well, so a part already present in `addr` is not repeated. */
export function mailingLine(m: {
  addr?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
}): string {
  const addr = (m.addr ?? '').trim();
  const has = (part: string) => addr.toUpperCase().includes(part.toUpperCase());
  const city = m.city?.trim() && !has(m.city.trim()) ? m.city.trim() : '';
  const tail = [m.state, m.zip]
    .map((p) => p?.trim() ?? '')
    .filter((p) => p && !has(p))
    .join(' ');
  return [addr, city, tail].filter(Boolean).join(', ');
}
