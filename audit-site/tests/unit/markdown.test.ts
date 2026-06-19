import { describe, it, expect } from 'vitest';
import { renderMarkdown, extractSignalSection } from '../../src/lib/markdown';

const DOSSIER = `# Title

intro paragraph

## Signal: \`tower_coords\`   ·   confidence: high
> verdict line

**1. What it is.** body one.

## Signal: \`tower_height\`   ·   confidence: high
> another verdict

**1. What it is.** body two.

<!-- audit-basis: commit abc -->
`;

describe('extractSignalSection', () => {
  it('pulls one signal block, heading through just before the next', () => {
    const sec = extractSignalSection(DOSSIER, 'tower_coords');
    expect(sec).not.toBeNull();
    expect(sec).toContain('## Signal: `tower_coords`');
    expect(sec).toContain('body one.');
    expect(sec).not.toContain('tower_height');
    expect(sec).not.toContain('body two.');
  });
  it('pulls the last block including trailing content', () => {
    const sec = extractSignalSection(DOSSIER, 'tower_height');
    expect(sec).toContain('body two.');
    expect(sec).toContain('audit-basis');
  });
  it('returns null for an unknown id', () => {
    expect(extractSignalSection(DOSSIER, 'nope')).toBeNull();
  });
});

describe('renderMarkdown — signal-id heading anchors', () => {
  it('uses the backtick signal id as the heading id (not the GitHub slug)', () => {
    const html = renderMarkdown('## Signal: `tower_coords`   ·   confidence: high', 'fcc-asr.md');
    expect(html).toContain('id="tower_coords"');
    expect(html).not.toContain('id="signal-tower_coords');
  });
  it('slugs ordinary headings', () => {
    const html = renderMarkdown('## Forward reconciliation', 'INDEX.md');
    expect(html).toContain('id="forward-reconciliation"');
  });
});

describe('renderMarkdown — link rewriting', () => {
  it('rewrites cross-file .md links onto the hash router', () => {
    const html = renderMarkdown('[FCC](./fcc-asr.md)', 'INDEX.md');
    expect(html).toContain('href="#/doc/fcc-asr.md"');
  });
  it('carries an anchor through to the doc route', () => {
    const html = renderMarkdown('[coords](fcc-asr.md#tower_coords)', 'INDEX.md');
    expect(html).toContain('href="#/doc/fcc-asr.md/tower_coords"');
  });
  it('keeps in-page #anchors inside the current doc', () => {
    const html = renderMarkdown('[see §5](#section-5)', 'verification-log.md');
    expect(html).toContain('href="#/doc/verification-log.md/section-5"');
  });
  it('opens external links in a new tab', () => {
    const html = renderMarkdown('[FCC](https://fcc.gov/x)', 'fcc-asr.md');
    expect(html).toContain('href="https://fcc.gov/x"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });
});
