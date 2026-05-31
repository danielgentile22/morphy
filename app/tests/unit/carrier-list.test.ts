import { describe, it, expect, afterEach } from 'vitest';
import { mount, unmount, flushSync } from 'svelte';
import CarrierList from '../../src/components/CarrierList.svelte';
import type { Carrier } from '../../src/lib/carrier';

// Mount the real component in jsdom via Svelte 5's built-in `mount` (no
// @testing-library needed — and the repo adds no test deps). Assert on
// stable hooks (data-testid / data-confidence / title / aria-label / text),
// not the scoped style class names.

let target: HTMLElement;
let app: Record<string, unknown> | null = null;

function render(carriers: Carrier[], compact = false): HTMLElement {
  target = document.createElement('div');
  document.body.appendChild(target);
  app = mount(CarrierList, { target, props: { carriers, compact } });
  flushSync();
  return target;
}

afterEach(() => {
  if (app) unmount(app);
  app = null;
  target?.remove();
});

const SAMPLE: Carrier[] = [
  { carrier_name: 'AT&T', callsign: 'KNKN566', license_expiry: '2031-10-01', confidence_tag: 'verified' },
  { carrier_name: 'ALLTEL Corporation', callsign: 'WPOI253', license_expiry: '2009-01-25', confidence_tag: 'likely' },
  { carrier_name: 'Rural Cellular', callsign: 'WQAA111', license_expiry: null, confidence_tag: 'possible' },
];

describe('CarrierList — populated', () => {
  it('renders one row per carrier with name + callsign', () => {
    const el = render(SAMPLE);
    const list = el.querySelector('[data-testid="carrier-list"]')!;
    expect(list).toBeTruthy();
    const text = list.textContent ?? '';
    expect(text).toContain('AT&T');
    expect(text).toContain('KNKN566');
    expect(text).toContain('ALLTEL Corporation');
    // license expiry shown when present, omitted when null
    expect(text).toContain('2031-10-01');
  });

  it('renders a confidence badge per tag with the tag word in the text', () => {
    const el = render(SAMPLE);
    const verified = el.querySelector('[data-confidence="verified"]')!;
    const likely = el.querySelector('[data-confidence="likely"]')!;
    const possible = el.querySelector('[data-confidence="possible"]')!;
    expect(verified.textContent?.trim()).toBe('Verified');
    expect(likely.textContent?.trim()).toBe('Likely');
    expect(possible.textContent?.trim()).toBe('Possible');
  });

  it('colours each badge by tone via a distinct class (not colour-alone)', () => {
    const el = render(SAMPLE);
    expect(el.querySelector('[data-confidence="verified"]')!.className).toContain('badge-verified');
    expect(el.querySelector('[data-confidence="likely"]')!.className).toContain('badge-likely');
    expect(el.querySelector('[data-confidence="possible"]')!.className).toContain('badge-possible');
  });

  it('explains each tag in a tooltip (title) + accessible aria-label', () => {
    const el = render(SAMPLE);
    const verified = el.querySelector('[data-confidence="verified"]')!;
    expect(verified.getAttribute('title')).toMatch(/ASR-number/i);
    expect(verified.getAttribute('aria-label')).toMatch(/Verified/);
    expect(verified.getAttribute('aria-label')).toMatch(/ASR-number/i);

    expect(el.querySelector('[data-confidence="likely"]')!.getAttribute('title')).toMatch(/100 m/);
    expect(el.querySelector('[data-confidence="possible"]')!.getAttribute('title')).toMatch(
      /100.*500 m/,
    );
  });

  it('keeps an unmapped carrier visible with its raw licensee name', () => {
    const el = render([
      { carrier_name: 'SOME RURAL TELEPHONE CO-OP', callsign: 'WXYZ999', license_expiry: null, confidence_tag: 'likely' },
    ]);
    expect(el.textContent).toContain('SOME RURAL TELEPHONE CO-OP');
  });
});

describe('CarrierList — empty state', () => {
  it('shows "No carriers identified" with a muted explanation (reads as normal)', () => {
    const el = render([]);
    const list = el.querySelector('[data-testid="carrier-list"]')!;
    expect(list).toBeTruthy();
    expect(list.textContent).toContain('No carriers identified');
    // a one-line explanation so an empty tower does not read as an error
    expect(list.textContent?.toLowerCase()).toContain('common');
    // no badges in the empty state
    expect(el.querySelector('[data-confidence]')).toBeNull();
  });
});
