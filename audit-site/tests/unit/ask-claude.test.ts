import { describe, it, expect } from 'vitest';
import { parseSSE } from '../../src/lib/ask-claude.svelte';
import { renderAnswer } from '../../src/lib/markdown';

describe('parseSSE', () => {
  it('parses a complete delta frame', () => {
    const { events, rest } = parseSSE('event: delta\ndata: {"text": "hi"}\n\n');
    expect(events).toEqual([{ event: 'delta', data: '{"text": "hi"}' }]);
    expect(rest).toBe('');
  });

  it('parses multiple frames in order in one buffer', () => {
    const buf =
      'event: delta\ndata: {"text": "a"}\n\n' +
      'event: delta\ndata: {"text": "b"}\n\n' +
      'event: done\ndata: {}\n\n';
    const { events } = parseSSE(buf);
    expect(events.map((e) => e.event)).toEqual(['delta', 'delta', 'done']);
    expect(events.map((e) => e.data)).toEqual(['{"text": "a"}', '{"text": "b"}', '{}']);
  });

  it('returns the trailing partial frame as rest, leaving it unparsed', () => {
    const { events, rest } = parseSSE('event: delta\ndata: {"text": "a"}\n\nevent: delta\ndata: {"te');
    expect(events).toHaveLength(1);
    expect(rest).toBe('event: delta\ndata: {"te');
  });

  it('is incremental — rest from one chunk completes with the next', () => {
    let buffer = 'event: delta\ndata: {"text": "he';
    let out = parseSSE(buffer);
    expect(out.events).toHaveLength(0);
    buffer = out.rest + 'llo"}\n\n';
    out = parseSSE(buffer);
    expect(out.events).toEqual([{ event: 'delta', data: '{"text": "hello"}' }]);
  });

  it('rejoins a multi-line data payload with newlines', () => {
    const { events } = parseSSE('event: delta\ndata: line one\ndata: line two\n\n');
    expect(events[0].data).toBe('line one\nline two');
  });
});

describe('renderAnswer', () => {
  it('renders markdown emphasis and lists', () => {
    const html = renderAnswer('**bold** and\n\n- one\n- two');
    expect(html).toContain('<strong>bold</strong>');
    expect(html).toContain('<li>one</li>');
  });

  it('drops raw HTML from model output (defense-in-depth)', () => {
    const html = renderAnswer('hello <script>alert(1)</script> world');
    expect(html).not.toContain('<script>');
  });
});
