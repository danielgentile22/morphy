import { test, expect, type Page } from '@playwright/test';

// Phase D — the URL is a shareable deep link: state, selected parcel,
// and active filters survive a reload.
const DB = 25_000;

async function waitReady(page: Page): Promise<void> {
  await page.getByTestId('filter-panel').waitFor({ state: 'visible', timeout: DB });
}

test('applying a filter writes it to the URL', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);

  await page.locator('[data-testid="filter-panel"] .chip', { hasText: 'LLC' }).click();
  await expect(page.getByTestId('filter-count')).toContainText('match', { timeout: DB });

  expect(page.url()).toContain('filters=');
  expect(decodeURIComponent(page.url())).toContain('ownerKind');
});

test('a filtered URL restores the filter on load', async ({ page }) => {
  const filters = encodeURIComponent(JSON.stringify({ ownerKind: ['llc'], hasTower: true }));
  await page.goto(`/?state=05&filters=${filters}`);
  await waitReady(page);

  // The chips reflect the restored filter, and the count is live.
  await expect(
    page.locator('[data-testid="filter-panel"] .chip.on', { hasText: 'LLC' }),
  ).toBeVisible({ timeout: DB });
  await expect(page.getByTestId('filter-count')).toContainText('match', { timeout: DB });
});

test('selecting a parcel writes ?selected= and restores it on reload', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);

  await page.locator('[data-testid="top-list"] button.row').first().click();
  const panel = page.getByTestId('details-panel');
  await expect(panel).toBeVisible();

  await expect(async () => {
    expect(page.url()).toContain('selected=');
  }).toPass({ timeout: DB });

  const selectedUrl = page.url();
  const parcelId = new URL(selectedUrl).searchParams.get('selected')!;
  expect(parcelId).toBeTruthy();

  // Reload the deep link — the same parcel is selected.
  await page.goto(selectedUrl);
  await waitReady(page);
  await expect(panel).toBeVisible({ timeout: DB });
  await expect(panel.locator('h2')).toContainText(parcelId, { timeout: DB });
});

test('switching state updates the URL', async ({ page }) => {
  await page.goto('/?state=05');
  await waitReady(page);

  await page.getByTestId('state-select').selectOption('30');
  await expect(page.getByTestId('summary-card')).toBeVisible({ timeout: DB });
  await expect(async () => {
    expect(page.url()).toContain('state=30');
  }).toPass({ timeout: DB });
});
