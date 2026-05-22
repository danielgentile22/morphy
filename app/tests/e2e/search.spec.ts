import { test, expect, type Page } from '@playwright/test';

// Phase C — owner / APN search and the DuckDB-enriched detail panel.
// The first DuckDB query pays a cold-start cost, so query-gated
// assertions get a generous timeout.
const DB = 25_000;
const AR_PARCEL_AREA: [number, number] = [-92.289, 34.746];

async function waitReady(page: Page): Promise<void> {
  await page.getByTestId('search-panel').waitFor({ state: 'visible', timeout: DB });
}

async function jumpTo(page: Page, zoom: number): Promise<void> {
  await page.evaluate(
    ([c, z]) =>
      new Promise<void>((res) => {
        const m = (window as any).__pilotMap;
        m.once('idle', () => res());
        m.jumpTo({ center: c, zoom: z });
      }),
    [AR_PARCEL_AREA, zoom] as const,
  );
}

test('owner search suggests clusters and filters by the chosen owner', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);

  await page.getByTestId('owner-search').fill('burch');
  const hits = page.getByTestId('owner-hits');
  await expect(hits).toBeVisible({ timeout: DB });
  await expect(hits.locator('li')).not.toHaveCount(0);

  await hits.locator('li button').first().click();
  // Choosing an owner applies an owner-cluster filter.
  const badge = page.getByTestId('filter-count');
  await expect(badge).toContainText('match', { timeout: DB });
});

test('APN search flies to and selects a parcel', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);

  await page.getByTestId('apn-search').fill('0001-05431-0000');
  await page.getByTestId('apn-search').press('Enter');

  const panel = page.getByTestId('details-panel');
  await expect(panel).toBeVisible({ timeout: DB });
  await expect(panel.locator('h2')).toContainText('0001-05431-0000');
});

test('APN search reports an unknown id', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);

  await page.getByTestId('apn-search').fill('NOT-A-REAL-APN');
  await page.getByTestId('apn-search').press('Enter');
  await expect(page.getByTestId('search-panel')).toContainText('No parcel with that ID', {
    timeout: DB,
  });
});

test('clicking a tile parcel enriches the panel with the full DuckDB row', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);

  // Isolate the parcel base layer, zoom in, click a parcel.
  for (const layer of ['towers', 'distress_overlays', 'interestingness_top_1000']) {
    await page.getByTestId(`layer-toggle-${layer}`).click();
  }
  await jumpTo(page, 13);
  const box = (await page.getByTestId('map').boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);

  const panel = page.getByTestId('details-panel');
  await expect(panel).toBeVisible();
  // owner_cluster_size is NOT a baked tile attribute — its row appears
  // only after the DuckDB full-row enrichment.
  await expect(panel.locator('[data-field="Parcels by this owner"] .v')).toBeVisible({
    timeout: DB,
  });
});

test('"see all parcels by this owner" applies an owner-cluster filter', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);

  // The #1 top-list parcel — its owner holds several parcels.
  await page.locator('[data-testid="top-list"] button.row').first().click();
  const seeAll = page.getByTestId('see-owner-parcels');
  await expect(seeAll).toBeVisible({ timeout: DB });
  await seeAll.click();

  await expect(page.getByTestId('filter-count')).toContainText('match', { timeout: DB });
});
