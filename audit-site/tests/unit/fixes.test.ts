import { describe, it, expect } from 'vitest';
import {
  groupFixes,
  overallProgress,
  isCheckable,
  BUCKET_ORDER,
  type Fix,
  type FixesDoc,
} from '../../src/lib/fixes';

function fix(id: string, bucket: Fix['bucket'], over: Partial<Fix> = {}): Fix {
  return {
    id,
    bucket,
    title: `fix ${id}`,
    signal: 'sig',
    card: 'T-00',
    action: 'do the thing',
    dossier: 'raw-column-sweep.md#misused_raw_columns',
    ...over,
  };
}

function doc(fixes: Fix[]): FixesDoc {
  return {
    schema_version: 1,
    generated: '2026-06-25',
    basis: 'test',
    note: 'test',
    buckets: { easy: 'E', medium: 'M', macro: 'X', inherent: 'I' },
    fixes,
  };
}

describe('isCheckable', () => {
  it('only easy + medium are tickable', () => {
    expect(isCheckable('easy')).toBe(true);
    expect(isCheckable('medium')).toBe(true);
    expect(isCheckable('macro')).toBe(false);
    expect(isCheckable('inherent')).toBe(false);
  });
});

describe('groupFixes', () => {
  it('groups in display order, drops empty buckets', () => {
    const groups = groupFixes(
      doc([fix('I1', 'inherent'), fix('E1', 'easy'), fix('E2', 'easy')]),
    );
    expect(groups.map((g) => g.bucket)).toEqual(['easy', 'inherent']);
    // display order is the canonical BUCKET_ORDER, not insertion order
    expect(groups[0].bucket).toBe(BUCKET_ORDER[0]);
  });

  it('counts done/total only for checkable buckets', () => {
    const groups = groupFixes(
      doc([
        fix('E1', 'easy', { status: 'done' }),
        fix('E2', 'easy', { status: 'todo' }),
        fix('X1', 'macro'),
      ]),
    );
    const easy = groups.find((g) => g.bucket === 'easy')!;
    expect(easy).toMatchObject({ checkable: true, done: 1, total: 2 });
    const macro = groups.find((g) => g.bucket === 'macro')!;
    // non-checkable buckets report 0/0 even though they hold fixes
    expect(macro).toMatchObject({ checkable: false, done: 0, total: 0 });
    expect(macro.fixes).toHaveLength(1);
  });
});

describe('overallProgress', () => {
  it('sums done/total across checkable buckets only', () => {
    const p = overallProgress(
      doc([
        fix('E1', 'easy', { status: 'done' }),
        fix('M1', 'medium', { status: 'done' }),
        fix('M2', 'medium', { status: 'todo' }),
        fix('X1', 'macro'), // ignored
        fix('I1', 'inherent'), // ignored
      ]),
    );
    expect(p).toEqual({ done: 2, total: 3 });
  });

  it('a missing status counts as not-done', () => {
    const p = overallProgress(doc([fix('E1', 'easy')]));
    expect(p).toEqual({ done: 0, total: 1 });
  });
});
