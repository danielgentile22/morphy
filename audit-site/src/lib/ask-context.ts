/**
 * Pure context builder for "Ask Claude" grounding (PRD #187 / #189).
 *
 * Turns what's on the page — the current route, the highlighted selection, a
 * bounded slice of the visible text, and the on-screen audit signals — into the
 * structured payload `POST /api/audit/ask` receives. Pure over its inputs (no
 * DOM, no store, no fetch): the component reads the page and the reactive store,
 * hands the raw material here, and this stays trivially unit-testable.
 *
 * The wire keys are snake_case to match the backend Pydantic model verbatim.
 */

import type { Signal } from './audit-data';
import type { Route } from './router.svelte';
import { filtersFromQuery, matchesFilters } from './signals';

/** The trust record for one on-screen signal — the five audit tags + the
 *  verdict, flattened from a {@link Signal} into the contract shape. */
export interface AskSignalRecord {
  id: string;
  confidence: string;
  upstream_origin: string;
  freshness_risk: string;
  derivation_risk: string;
  verifiability: string;
  verdict: string;
}

/** One prior conversation turn echoed back so the stateless backend keeps
 *  context across follow-ups. */
export interface AskThreadTurn {
  role: 'user' | 'assistant';
  content: string;
}

/** The `POST /api/audit/ask` request body (slice 2 grounding). */
export interface AskContextPayload {
  question: string;
  route: string;
  selection: string | null;
  visible_text: string;
  signals: AskSignalRecord[];
  thread: AskThreadTurn[];
}

// Client-side bound on the visible-text slice (AC: "visible text is bounded
// client-side"). The assembler truncates again server-side as defense-in-depth;
// bounding here keeps the request small on the wire.
export const MAX_VISIBLE_TEXT_CHARS = 6000;

/** Flatten a Signal into the wire record (id + the five tags + verdict). */
export function toSignalRecord(s: Signal): AskSignalRecord {
  return {
    id: s.id,
    confidence: s.tags.confidence,
    upstream_origin: s.tags.upstream_origin,
    freshness_risk: s.tags.freshness_risk,
    derivation_risk: s.tags.derivation_risk,
    verifiability: s.tags.verifiability,
    verdict: s.verdict,
  };
}

/** A short human label for the current route — orients Claude to the page the
 *  reader is on ("Signal: owner_name@12", "Signals browser", "Data Catalog", …). */
export function routeLabel(route: Route): string {
  switch (route.name) {
    case 'overview':
      return 'Overview';
    case 'catalog':
      return route.anchor ? `Data Catalog — ${route.anchor}` : 'Data Catalog';
    case 'freshness':
      return 'What needs updating';
    case 'signals':
      return 'Signals browser';
    case 'signal':
      return `Signal: ${route.id}`;
    case 'cards':
      return 'Audit cards';
    case 'card':
      return `Audit card: ${route.id}`;
    case 'doc':
      return `Dossier: ${route.file}`;
    default:
      return '';
  }
}

/**
 * The signals actually on screen for a route, derived purely from the route +
 * the loaded signal set:
 *   - a signal detail page → just that signal,
 *   - an audit card → that card's signals,
 *   - the signals browser → the set matching its URL filter (exactly what's listed),
 *   - the catalog → every signal (the whole catalog is the subject),
 *   - anything else (overview / freshness / cards / doc) → none.
 * The count is capped downstream by the assembler.
 */
export function onScreenSignals(
  route: Route,
  signals: Signal[],
  signalById: Map<string, Signal>,
): Signal[] {
  switch (route.name) {
    case 'signal': {
      const s = signalById.get(route.id);
      return s ? [s] : [];
    }
    case 'card':
      return signals.filter((s) => s.card === route.id);
    case 'signals': {
      const f = filtersFromQuery(route.query);
      return signals.filter((s) => matchesFilters(s, f));
    }
    case 'catalog':
      return signals;
    default:
      return [];
  }
}

/**
 * Build the grounded request payload. Pure: drops an empty/whitespace selection
 * to `null` (→ a question-only payload), bounds the visible text client-side,
 * and flattens signals to the wire record. The thread is passed through as-is
 * (the assembler clamps it to the last K turns).
 */
export function buildAskContext(input: {
  question: string;
  route: string;
  selection: string | null;
  visibleText: string;
  signals: Signal[];
  thread: AskThreadTurn[];
}): AskContextPayload {
  const trimmed = input.selection?.trim();
  return {
    question: input.question,
    route: input.route,
    selection: trimmed ? trimmed : null,
    visible_text:
      input.visibleText.length > MAX_VISIBLE_TEXT_CHARS
        ? input.visibleText.slice(0, MAX_VISIBLE_TEXT_CHARS)
        : input.visibleText,
    signals: input.signals.map(toSignalRecord),
    thread: input.thread,
  };
}
