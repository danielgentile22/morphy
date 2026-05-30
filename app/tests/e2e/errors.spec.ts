import { test, expect } from '@playwright/test';

// Error paths must render an actionable message — never a blank screen or
// a crash. Each test injects a failure with network interception.

test('a failed layer fetch disables its toggle, the app still loads', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (e) => pageErrors.push(e.message));

  // Make one layer's GeoJSON unreachable.
  await page.route('**/composite/05/distress_overlays.geojson', (route) => route.abort());
  await page.goto('/?state=05');

  // The app still boots — a single missing layer is tolerated.
  await expect(page.locator('h1')).toHaveText('Arkansas');
  await expect(page.getByTestId('summary-card')).toBeVisible();

  // The distress-overlays toggle is disabled and marked unavailable.
  const toggle = page.getByTestId('layer-toggle-distress_overlays');
  await expect(toggle).toBeDisabled();
  await expect(page.locator('.toggle', { has: toggle })).toContainText('unavailable');

  expect(pageErrors).toEqual([]);
});

test('an unreachable index.json shows an actionable error screen', async ({ page }) => {
  await page.route('**/composite/index.json', (route) => route.abort());
  await page.goto('/');

  const err = page.getByTestId('boot-error');
  await expect(err).toBeVisible();
  await expect(err).toContainText('Could not load the map data');
  // The message names the data server — an actionable hint, not a blank screen.
  await expect(err).toContainText('serve.py');
});

test('a malformed catalog shows an error screen', async ({ page }) => {
  await page.route('**/composite/05/catalog.json', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"oops":true}' }),
  );
  await page.goto('/?state=05');

  const err = page.getByTestId('boot-error');
  await expect(err).toBeVisible();
  await expect(err).toContainText('catalog');
});
