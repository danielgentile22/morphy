import { describe, it, expect, afterEach } from 'vitest';
import { mount, unmount, flushSync } from 'svelte';
import DetailsPanel from '../../src/components/DetailsPanel.svelte';
import { app } from '../../src/lib/stores.svelte';
import { scoring } from '../../src/lib/scoring-store.svelte';

// The "Score factors" bars are the baked default-profile components; custom
// scoring ranks by a different owner-grained formula (audit fix M-g / #214).
// Assert the panel discloses that whenever custom scoring is active — and
// stays note-free under the default config.

let target: HTMLElement;
let panel: Record<string, unknown> | null = null;

const PARCEL_PROPS = {
  interestingness_components: JSON.stringify({ distress_tier: 0.3, has_tower: 0.2 }),
};

function render(): HTMLElement {
  target = document.createElement('div');
  document.body.appendChild(target);
  panel = mount(DetailsPanel, { target });
  flushSync();
  return target;
}

afterEach(() => {
  if (panel) unmount(panel);
  panel = null;
  target?.remove();
  app.clearSelection();
  scoring.reset();
});

describe('DetailsPanel score factors under scoring modes', () => {
  it('renders bars with no disclosure note under default scoring', () => {
    app.setSelection({ kind: 'parcel', props: PARCEL_PROPS });
    const el = render();
    expect(el.textContent).toContain('Score factors');
    expect(el.querySelector('[data-testid="score-factors-note"]')).toBeNull();
  });

  it('discloses the default profile when a custom ranking is active', () => {
    app.setSelection({ kind: 'parcel', props: PARCEL_PROPS });
    scoring.setWeight('towers', 0.8);
    const el = render();
    const note = el.querySelector('[data-testid="score-factors-note"]');
    expect(note).not.toBeNull();
    expect(note?.textContent).toContain('Default score profile');
    // The bars themselves still render — the note discloses, it doesn't hide.
    expect(el.textContent).toContain('Score factors');
  });

  it('removes the note when scoring resets to the default profile', () => {
    app.setSelection({ kind: 'parcel', props: PARCEL_PROPS });
    scoring.setWeight('towers', 0.8);
    const el = render();
    expect(el.querySelector('[data-testid="score-factors-note"]')).not.toBeNull();
    scoring.reset();
    flushSync();
    expect(el.querySelector('[data-testid="score-factors-note"]')).toBeNull();
  });
});
