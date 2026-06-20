/**
 * M1 · Catalog builder (deep module). Pure `(AuditIndex, CatalogConfig) →
 * CatalogModel`. Turns the flat, per-state signal list from `index.json` into
 * the grouped, plain-English catalog the co-founder view renders:
 *
 *  - Collapses the four per-state variants of a signal (`owner_name@05/@12/@30/
 *    @54`) into one logical data point keyed by `baseSignalId`, carrying a
 *    per-state cell (trust + the underlying signal) for the drill-in. National
 *    signals (no `@NN`) stay single.
 *  - Assigns each point to a group via the config; a base id the config doesn't
 *    know lands in the synthetic "Newly added" group (never dropped).
 *  - Rolls up, per group, a headline trust (most-common, ties-to-lower) and the
 *    biggest caveat (the lowest-confidence point's verdict) — produced here to
 *    keep M1 whole; first *shown* by the Overview slice.
 *  - Deterministic ordering: groups in configured order (Newly-added first when
 *    non-empty); points within a group weakest-trust-first.
 *
 * Reads only `index.signals`; every per-point fact comes from the file verbatim
 * (the auto-populate contract — see audit-data.ts). The curated framing lives in
 * catalog-config.ts; vocab → friendly strings in catalog-language.ts.
 */

import type { AuditIndex, Signal, SignalTags } from './audit-data';
import { baseSignalId, stateOf, STATE_NAMES, STATE_ABBR } from './signals';
import { defaultCatalogConfig, type CatalogConfig, type GroupDef } from './catalog-config';

const TRUST_RANK: Record<string, number> = { low: 0, medium: 1, high: 2 };

/** Weakest-first rank. An unknown/unseen confidence ranks below `low` (-1) so a
 *  point with an evolved vocab value surfaces first rather than hiding among the
 *  high-trust rows — the conservative reading the audit is built on. */
function trustRank(confidence: string): number {
  return TRUST_RANK[confidence] ?? -1;
}

/** One state's cell of a collapsed per-state data point. */
export interface StateCell {
  fips: string;
  name: string;
  confidence: string;
  /** The underlying per-state signal — the drill-in link target. */
  signal: Signal;
}

/** A logical data point: one signal, or the collapse of its per-state variants. */
export interface DataPoint {
  baseId: string;
  groupId: string;
  /** Plain meaning from the config; `null` when the id is unrecognised. */
  meaning: string | null;
  /** False → rendered in the "Newly added" group with its raw verdict. */
  recognised: boolean;
  isPerState: boolean;
  /** Representative facts = the *weakest* underlying signal, so the single row
   *  badge / where-from / how-current describe the state you can trust least. */
  confidence: string;
  tags: SignalTags;
  verdict: string;
  dossier: string;
  /** One cell per state for a per-state point (fips-sorted); `[]` for national. */
  states: StateCell[];
}

export interface CatalogGroup {
  def: GroupDef;
  points: DataPoint[];
  /** Most-common trust among the group's points; ties break to the lower trust. */
  headlineTrust: string;
  /** The lowest-confidence point's verdict, or null for an empty group. */
  biggestCaveat: string | null;
  /** Per-trust-value counts across the group's points. */
  counts: Record<string, number>;
}

export interface CatalogModel {
  groups: CatalogGroup[];
}

/** The pilot's four states in display order (fips-ascending = AR/FL/MT/WV) — the
 *  fixed columns of a per-state trust strip. */
const STRIP_FIPS = ['05', '12', '30', '54'] as const;

/** One column of a per-state trust strip: always one per AR/FL/MT/WV, in order.
 *  `cell` is null when the field has no signal for that state, so the strip shows
 *  an honest gap rather than silently collapsing to three columns. */
export interface StripColumn {
  fips: string;
  abbr: string;
  name: string;
  cell: StateCell | null;
}

/** Project a data point's present per-state cells onto the fixed 4-column
 *  AR/FL/MT/WV grid the trust strip renders. National (non-per-state) points
 *  return `[]` → no strip. Pure; the per-state trust comes straight from each
 *  cell's underlying signal (the auto-populate contract). */
export function stateStrip(point: DataPoint): StripColumn[] {
  if (!point.isPerState) return [];
  const byFips = new Map(point.states.map((c) => [c.fips, c]));
  return STRIP_FIPS.map((fips) => ({
    fips,
    abbr: STATE_ABBR[fips] ?? fips,
    name: STATE_NAMES[fips] ?? fips,
    cell: byFips.get(fips) ?? null,
  }));
}

/** The `#/doc/<file>/<anchor>` deep-link target for a point's "Why this rating"
 *  expander. Splits the representative signal's `file.md#anchor` dossier ref the
 *  same way SignalDetail does. The dossier `## Signal:` heading keys on the BASE
 *  id (`owner_name`, never the `@NN`-suffixed signal id), so a missing anchor
 *  falls back to `baseId` — correct for national and per-state alike. Because a
 *  per-state point's representative is its *weakest* state, this resolves to that
 *  state's per-state dossier section. Pure. */
export function dossierTarget(point: DataPoint): { file: string; anchor: string } {
  const [file, anchor] = point.dossier.split('#');
  return { file, anchor: anchor || point.baseId };
}

export function buildCatalog(
  index: AuditIndex,
  config: CatalogConfig = defaultCatalogConfig,
): CatalogModel {
  // 1. Collapse the per-state variants: bucket every signal by its base id.
  const byBase = new Map<string, Signal[]>();
  for (const s of index.signals) {
    const b = baseSignalId(s.id);
    const list = byBase.get(b);
    if (list) list.push(s);
    else byBase.set(b, [s]);
  }

  // 2. One DataPoint per base id.
  const points: DataPoint[] = [];
  for (const [baseId, sigs] of byBase) {
    const stateSigs = sigs.filter((s) => stateOf(s.id) !== null);
    const isPerState = stateSigs.length > 0;

    // Representative = the weakest underlying signal (lowest trust; id tie-break).
    const rep = [...sigs].sort(
      (a, b) =>
        trustRank(a.tags.confidence) - trustRank(b.tags.confidence) || a.id.localeCompare(b.id),
    )[0];

    const states: StateCell[] = stateSigs
      .map((s) => {
        const fips = stateOf(s.id) as string;
        return { fips, name: STATE_NAMES[fips] ?? fips, confidence: s.tags.confidence, signal: s };
      })
      .sort((a, b) => a.fips.localeCompare(b.fips));

    const entry = config.entries[baseId];
    points.push({
      baseId,
      groupId: entry ? entry.group : config.newlyAdded.id,
      meaning: entry ? entry.meaning : null,
      recognised: Boolean(entry),
      isPerState,
      confidence: rep.tags.confidence,
      tags: rep.tags,
      verdict: rep.verdict,
      dossier: rep.dossier,
      states,
    });
  }

  // 3. Bucket points by group id.
  const byGroup = new Map<string, DataPoint[]>();
  for (const p of points) {
    const list = byGroup.get(p.groupId);
    if (list) list.push(p);
    else byGroup.set(p.groupId, [p]);
  }

  // 4. Assemble groups in order: Newly-added first, then the curated order.
  //    Empty groups are dropped so a zero-signal card never yields empty rows.
  const orderedDefs = [config.newlyAdded, ...[...config.groups].sort((a, b) => a.order - b.order)];
  const groups: CatalogGroup[] = [];
  for (const def of orderedDefs) {
    const gp = byGroup.get(def.id);
    if (!gp || gp.length === 0) continue;
    const sorted = [...gp].sort(
      (a, b) => trustRank(a.confidence) - trustRank(b.confidence) || a.baseId.localeCompare(b.baseId),
    );
    groups.push({
      def,
      points: sorted,
      headlineTrust: headlineTrust(sorted),
      biggestCaveat: sorted[0].verdict, // weakest-first → [0] is the lowest-confidence point
      counts: countTrust(sorted),
    });
  }

  return { groups };
}

function countTrust(points: DataPoint[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const p of points) counts[p.confidence] = (counts[p.confidence] ?? 0) + 1;
  return counts;
}

/** Most-common trust value; on a tie, the lower-ranked (more conservative) one. */
function headlineTrust(points: DataPoint[]): string {
  const counts = countTrust(points);
  let best: string | null = null;
  let bestN = -1;
  for (const [trust, n] of Object.entries(counts)) {
    if (n > bestN || (n === bestN && best !== null && trustRank(trust) < trustRank(best))) {
      best = trust;
      bestN = n;
    }
  }
  return best ?? 'unknown';
}
