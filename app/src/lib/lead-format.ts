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
