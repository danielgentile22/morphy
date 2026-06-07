import { test, expect, type Page } from '@playwright/test';

// Slice 6 (#52) — the top-bar owner-name / ASR search "jumps to the match":
// an owner hit opens its Lead; an ASR hit flies the map to that tower. Runs
// against the static read-layer (towers + owners_filter.json), no backend.
const MAP = 25_000;

async function waitReady(page: Page): Promise<void> {
  await page.getByTestId('top-filter-bar').first().waitFor({ state: 'visible', timeout: MAP });
  await page.waitForFunction(() => !!(window as any).__pilotMap, null, { timeout: MAP });
}

function search(page: Page) {
  return page.getByRole('main').getByTestId('owner-search');
}

test('owner-name search surfaces matching owners and opens a Lead', async ({ page }) => {
  await page.goto('/#/explore');
  await waitReady(page);

  await search(page).fill('weyerhaeuser');
  const hits = page.getByRole('main').getByTestId('search-hits');
  await expect(hits).toBeVisible({ timeout: MAP });
  await expect(hits.getByText(/WEYERHAEUSER/i).first()).toBeVisible();

  await hits.locator('.hit').first().click();
  // Jumps to the matched owner's Lead (the shareable detail route).
  await expect(page).toHaveURL(/#\/lead\//, { timeout: MAP });
  await expect(page.getByTestId('lead-page')).toBeVisible();
});

test('ASR search surfaces tower matches and flies the map to one', async ({ page }) => {
  await page.goto('/#/explore');
  await waitReady(page);
  await page.waitForFunction(() => (window as any).__pilotMap.isStyleLoaded());

  const center = () =>
    page.evaluate(() => {
      const c = (window as any).__pilotMap.getCenter();
      return [Math.round(c.lng * 100) / 100, Math.round(c.lat * 100) / 100];
    });
  const before = await center();

  await search(page).fill('1064');
  const hits = page.getByRole('main').getByTestId('search-hits');
  await expect(hits.getByText(/ASR/).first()).toBeVisible({ timeout: MAP });
  await hits.locator('.hit').first().click();

  // The map jumps to the tower (center moves to its coordinate).
  await expect.poll(center, { timeout: MAP }).not.toEqual(before);
});
