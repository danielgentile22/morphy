import { test, expect, type Page } from '@playwright/test';

// Phase C — the DuckDB-backed filter UI: live count, the map fade, reset.
// The first filter query pays the DuckDB-WASM cold-start cost (a few
// seconds), so query-gated assertions get a generous timeout.
const DB = 25_000;

async function waitReady(page: Page): Promise<void> {
  await page.getByTestId('filter-panel').waitFor({ state: 'visible', timeout: DB });
}

function countNumber(text: string): number {
  const m = text.match(/([\d,]+)/);
  return m ? Number(m[1].replace(/,/g, '')) : NaN;
}

test('an owner-kind filter updates the live count badge', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);

  const badge = page.getByTestId('filter-count');
  await expect(badge).toContainText('no filter');
  const total = countNumber((await badge.textContent())!);

  await page.locator('[data-testid="filter-panel"] .chip', { hasText: 'LLC' }).click();
  await expect(badge).toContainText('match', { timeout: DB });

  const matched = countNumber((await badge.textContent())!);
  expect(matched).toBeGreaterThan(0);
  expect(matched).toBeLessThan(total);
});

test('compound filters narrow the count further', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);
  const badge = page.getByTestId('filter-count');

  await page.locator('[data-testid="filter-panel"] .chip', { hasText: 'LLC' }).click();
  await expect(badge).toContainText('match', { timeout: DB });
  const llcOnly = countNumber((await badge.textContent())!);

  await page.locator('[data-testid="filter-panel"] .chip', { hasText: 'Distressed' }).click();
  await expect(badge).toContainText('match', { timeout: DB });
  const llcAndDistressed = countNumber((await badge.textContent())!);

  expect(llcAndDistressed).toBeGreaterThan(0);
  expect(llcAndDistressed).toBeLessThanOrEqual(llcOnly);
});

test('a filter fades non-matching parcels; reset restores them', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);
  const badge = page.getByTestId('filter-count');

  // With a filter active the parcels fill gains a feature-state branch
  // (matches bright, the rest faded); 'missing' until the layer exists.
  const fadeMode = () =>
    page.evaluate(() => {
      const m = (window as any).__pilotMap;
      if (!m || !m.getLayer('parcels:fill')) return 'missing';
      const expr = m.getPaintProperty('parcels:fill', 'fill-opacity');
      return JSON.stringify(expr).includes('feature-state') ? 'filtered' : 'plain';
    });
  await expect.poll(fadeMode, { timeout: DB }).toBe('plain');

  await page.locator('[data-testid="filter-panel"] .chip', { hasText: 'LLC' }).click();
  await expect(badge).toContainText('match', { timeout: DB });
  await expect.poll(fadeMode, { timeout: DB }).toBe('filtered');

  await page.getByTestId('reset-filters').click();
  await expect(badge).toContainText('no filter', { timeout: DB });
  await expect.poll(fadeMode, { timeout: DB }).toBe('plain');
});

test('reset all is disabled until a filter is active', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);

  await expect(page.getByTestId('reset-filters')).toBeDisabled();
  await page.locator('[data-testid="filter-panel"] .chip', { hasText: 'LLC' }).click();
  await expect(page.getByTestId('reset-filters')).toBeEnabled();
});

test('the score slider filters by interestingness', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);
  const badge = page.getByTestId('filter-count');

  await page.getByTestId('score-slider').fill('0.8');
  await expect(badge).toContainText('match', { timeout: DB });
  const matched = countNumber((await badge.textContent())!);
  expect(matched).toBeGreaterThan(0);
});
