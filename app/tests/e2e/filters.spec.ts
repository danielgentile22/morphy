import { test, expect, type Page } from '@playwright/test';

// Slice 6 (#52) — the top filter bar narrows the structures-first tower layer.
// Runs against the static read-layer only (towers + owners_filter.json); the
// Candidates-list side of the same shared FilterModel needs the backend and is
// covered by the FilterModel unit tests + manual verification.
const MAP = 25_000;

async function waitReady(page: Page): Promise<void> {
  await page.getByTestId('top-filter-bar').first().waitFor({ state: 'visible', timeout: MAP });
  await page.waitForFunction(() => !!(window as any).__pilotMap, null, { timeout: MAP });
}

/** Approximate towers currently on the map: individual points + cluster sums. */
function towerCount(page: Page): Promise<number> {
  return page.evaluate(() => {
    const m = (window as any).__pilotMap;
    const r = m.queryRenderedFeatures({ layers: ['towers-point', 'towers-clusters'] });
    let n = 0;
    for (const f of r) n += f.properties.point_count || 1;
    return n;
  });
}

test('the slim top filter bar shows the high-use filters + search', async ({ page }) => {
  await page.goto('/#/explore');
  await waitReady(page);
  const bar = page.getByRole('main').getByTestId('top-filter-bar');
  for (const name of ['State', 'Distress', 'Structure', 'Score', 'More filters']) {
    await expect(bar.getByRole('button', { name: new RegExp(name) })).toBeVisible();
  }
  await expect(bar.getByTestId('owner-search')).toBeVisible();
  // The dropped parcel-noise filters are gone from the UI entirely.
  await expect(page.getByTestId('filter-panel')).toHaveCount(0);
});

test('a state filter narrows the tower layer (shared FilterModel)', async ({ page }) => {
  await page.goto('/#/explore');
  await waitReady(page);
  await page.waitForFunction(() => (window as any).__pilotMap.isStyleLoaded());
  await expect.poll(() => towerCount(page), { timeout: MAP }).toBeGreaterThan(0);
  const before = await towerCount(page);

  const bar = page.getByRole('main').getByTestId('top-filter-bar');
  await bar.getByRole('button', { name: /State/ }).click();
  await page.getByRole('button', { name: 'MT', exact: true }).click();

  // The bar marks State active, and the tower layer shrinks to MT-linked owners.
  await expect(bar.getByRole('button', { name: /State · 1/ })).toBeVisible();
  await expect.poll(() => towerCount(page), { timeout: MAP }).toBeLessThan(before);
});

test('reset is disabled until a filter is active, then clears it', async ({ page }) => {
  await page.goto('/#/explore');
  await waitReady(page);
  const bar = page.getByRole('main').getByTestId('top-filter-bar');

  await expect(bar.getByTestId('reset-filters')).toBeDisabled();
  await bar.getByRole('button', { name: /Score/ }).click();
  await bar.getByTestId('score-slider').fill('0.8');
  await expect(bar.getByTestId('reset-filters')).toBeEnabled();

  await bar.getByTestId('reset-filters').click();
  await expect(bar.getByTestId('reset-filters')).toBeDisabled();
});
