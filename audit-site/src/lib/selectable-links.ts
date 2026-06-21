/**
 * Make text inside clickable cards/links drag-selectable (PRD #187 follow-up).
 *
 * The catalog is card-heavy: most content sits inside `<a>` tiles (the Overview
 * group cards, signal rows, etc.). When a drag to select text *starts inside an
 * anchor*, the browser begins its native link-drag instead of a text selection,
 * so the selection never forms — and "highlight → ✨ Ask Claude" silently fails
 * on exactly the content people most want to ask about. (Verified: the bubble
 * itself works for card text; only the human's drag-select was being eaten.)
 *
 * We let selection win, globally and delegated (so it covers the SPA's
 * re-rendered content and every link class without per-component edits):
 *
 *  1. On pointer-down over a content link (inside `<main>`), mark that anchor
 *     `draggable = false` so the ensuing drag selects text instead of dragging
 *     the link. Set just-in-time per press → robust across browsers and immune
 *     to re-renders, with no MutationObserver.
 *  2. Swallow the click-through when the click lands on text the user just
 *     drag-selected *inside that same link*, so a deliberate highlight never
 *     navigates away. A plain click (no surviving selection in the link) still
 *     navigates normally — a mouse-down collapses any prior selection, so a
 *     real click reaches this guard with nothing selected.
 */

/**
 * True when navigation through `anchor` should be suppressed because there is
 * an active (non-empty) text selection sitting inside it — i.e. the user
 * drag-selected text in this link rather than clicking it. Pure: the click
 * guard's decision, unit-testable without a DOM.
 */
export function selectionIsInsideLink(sel: Selection | null, anchor: Element | null): boolean {
  if (anchor === null || sel === null || sel.isCollapsed) return false;
  if (sel.toString().trim() === '') return false;
  const node = sel.anchorNode;
  return node !== null && anchor.contains(node);
}

/** Install the delegated handlers on `doc`; returns a cleanup that removes them
 *  (wired through the app shell's `onMount`). */
export function enableTextSelectionInLinks(doc: Document = document): () => void {
  const onPointerDown = (e: Event): void => {
    const anchor = (e.target as Element | null)?.closest?.('a[href]') ?? null;
    // Only content links — leave nav/footer/external link-dragging untouched.
    if (anchor && anchor.closest('main')) (anchor as HTMLElement).draggable = false;
  };
  const onClick = (e: Event): void => {
    const anchor = (e.target as Element | null)?.closest?.('a[href]') ?? null;
    if (selectionIsInsideLink(doc.getSelection(), anchor)) {
      e.preventDefault();
      e.stopPropagation();
    }
  };
  doc.addEventListener('pointerdown', onPointerDown, true);
  doc.addEventListener('click', onClick, true);
  return () => {
    doc.removeEventListener('pointerdown', onPointerDown, true);
    doc.removeEventListener('click', onClick, true);
  };
}
