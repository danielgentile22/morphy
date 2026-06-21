import { describe, it, expect } from 'vitest';
import { selectionIsInsideLink } from '../../src/lib/selectable-links';

// Minimal structural fakes — no DOM. A Selection is just { isCollapsed,
// toString, anchorNode }; an anchor is just { contains }.
function sel(over: Partial<{ isCollapsed: boolean; text: string; anchorNode: unknown }> = {}): Selection {
  const node = 'anchorNode' in over ? over.anchorNode : {};
  return {
    isCollapsed: over.isCollapsed ?? false,
    anchorNode: node,
    toString: () => over.text ?? 'highlighted text',
  } as unknown as Selection;
}

function anchor(contains: boolean): Element {
  return { contains: () => contains } as unknown as Element;
}

describe('selectionIsInsideLink', () => {
  it('true when a non-empty selection sits inside the anchor', () => {
    const node = {};
    const s = sel({ anchorNode: node });
    const a = { contains: (n: unknown) => n === node } as unknown as Element;
    expect(selectionIsInsideLink(s, a)).toBe(true);
  });

  it('false when there is no anchor (clicked outside any link)', () => {
    expect(selectionIsInsideLink(sel(), null)).toBe(false);
  });

  it('false when the selection is collapsed (a plain click, not a drag-select)', () => {
    expect(selectionIsInsideLink(sel({ isCollapsed: true }), anchor(true))).toBe(false);
  });

  it('false when the selection is whitespace only', () => {
    expect(selectionIsInsideLink(sel({ text: '   ' }), anchor(true))).toBe(false);
  });

  it('false when the selection lives outside the clicked anchor', () => {
    // Selection exists, but in a different element → clicking this link navigates.
    expect(selectionIsInsideLink(sel(), anchor(false))).toBe(false);
  });

  it('false when there is no selection at all', () => {
    expect(selectionIsInsideLink(null, anchor(true))).toBe(false);
  });

  it('false when the selection has no anchor node', () => {
    expect(selectionIsInsideLink(sel({ anchorNode: null }), anchor(true))).toBe(false);
  });
});
