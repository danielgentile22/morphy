import { describe, it, expect } from 'vitest';
import type { Signal } from '../../src/lib/audit-data';
import {
  buildAskContext,
  MAX_VISIBLE_TEXT_CHARS,
  onScreenSignals,
  routeLabel,
  toSignalRecord,
} from '../../src/lib/ask-context';

function sig(id: string, over: Partial<Signal> = {}): Signal {
  return {
    id,
    card: 'c1',
    surface: 's',
    priority: null,
    tags: {
      confidence: 'high',
      upstream_origin: 'official_filing',
      freshness_risk: 'low',
      derivation_risk: 'low',
      verifiability: 'high',
    },
    verdict: 'trustworthy',
    dossier: 'f.md#x',
    ...over,
  };
}

describe('toSignalRecord', () => {
  it('flattens a Signal into the five tags + verdict', () => {
    expect(toSignalRecord(sig('owner_name@12'))).toEqual({
      id: 'owner_name@12',
      confidence: 'high',
      upstream_origin: 'official_filing',
      freshness_risk: 'low',
      derivation_risk: 'low',
      verifiability: 'high',
      verdict: 'trustworthy',
    });
  });
});

describe('buildAskContext', () => {
  it('builds the payload from a selection + on-screen signals', () => {
    const payload = buildAskContext({
      question: 'why high?',
      route: 'Signal: owner_name@12',
      selection: '  owner_name  ',
      visibleText: 'page text',
      signals: [sig('owner_name@12'), sig('foo@05')],
      thread: [],
    });
    expect(payload.question).toBe('why high?');
    expect(payload.route).toBe('Signal: owner_name@12');
    expect(payload.selection).toBe('owner_name'); // trimmed
    expect(payload.visible_text).toBe('page text');
    // The on-screen signal ids ride along, flattened to the wire record.
    expect(payload.signals.map((s) => s.id)).toEqual(['owner_name@12', 'foo@05']);
    expect(payload.signals[0].confidence).toBe('high');
  });

  it('drops an empty / whitespace selection to null (question-only payload)', () => {
    const blank = buildAskContext({
      question: 'q',
      route: 'Overview',
      selection: '   ',
      visibleText: '',
      signals: [],
      thread: [],
    });
    expect(blank.selection).toBeNull();
    expect(blank.signals).toEqual([]);

    const none = buildAskContext({
      question: 'q',
      route: 'Overview',
      selection: null,
      visibleText: '',
      signals: [],
      thread: [],
    });
    expect(none.selection).toBeNull();
  });

  it('bounds the visible text client-side', () => {
    const long = 'x'.repeat(MAX_VISIBLE_TEXT_CHARS + 500);
    const payload = buildAskContext({
      question: 'q',
      route: '',
      selection: null,
      visibleText: long,
      signals: [],
      thread: [],
    });
    expect(payload.visible_text.length).toBe(MAX_VISIBLE_TEXT_CHARS);
  });

  it('passes the thread through unchanged (the assembler clamps it)', () => {
    const thread = [
      { role: 'user' as const, content: 'a' },
      { role: 'assistant' as const, content: 'b' },
    ];
    const payload = buildAskContext({
      question: 'q',
      route: '',
      selection: null,
      visibleText: '',
      signals: [],
      thread,
    });
    expect(payload.thread).toEqual(thread);
  });
});

describe('onScreenSignals', () => {
  const signals = [
    sig('a@12', { card: 'c1' }),
    sig('b@05', { card: 'c2' }),
    sig('c@12', { card: 'c1' }),
  ];
  const byId = new Map(signals.map((s) => [s.id, s]));

  it('returns just the one signal on a signal detail route', () => {
    expect(onScreenSignals({ name: 'signal', id: 'b@05' }, signals, byId).map((s) => s.id)).toEqual(
      ['b@05'],
    );
  });

  it('returns nothing for an unknown signal id', () => {
    expect(onScreenSignals({ name: 'signal', id: 'zzz' }, signals, byId)).toEqual([]);
  });

  it("returns a card's signals on a card route", () => {
    expect(onScreenSignals({ name: 'card', id: 'c1' }, signals, byId).map((s) => s.id)).toEqual([
      'a@12',
      'c@12',
    ]);
  });

  it('applies the URL filter on the signals-browser route', () => {
    expect(
      onScreenSignals({ name: 'signals', query: 'state=05' }, signals, byId).map((s) => s.id),
    ).toEqual(['b@05']);
  });

  it('returns every signal on the catalog route, and none elsewhere', () => {
    expect(onScreenSignals({ name: 'catalog', anchor: null }, signals, byId)).toHaveLength(3);
    expect(onScreenSignals({ name: 'overview' }, signals, byId)).toEqual([]);
    expect(onScreenSignals({ name: 'freshness' }, signals, byId)).toEqual([]);
  });
});

describe('routeLabel', () => {
  it('labels each route for the prompt', () => {
    expect(routeLabel({ name: 'overview' })).toBe('Overview');
    expect(routeLabel({ name: 'catalog', anchor: null })).toBe('Data Catalog');
    expect(routeLabel({ name: 'catalog', anchor: 'parcels' })).toBe('Data Catalog — parcels');
    expect(routeLabel({ name: 'signals', query: '' })).toBe('Signals browser');
    expect(routeLabel({ name: 'signal', id: 'owner_name@12' })).toBe('Signal: owner_name@12');
    expect(routeLabel({ name: 'card', id: 'c1' })).toBe('Audit card: c1');
    expect(routeLabel({ name: 'doc', file: 'x.md', anchor: null })).toBe('Dossier: x.md');
  });
});
