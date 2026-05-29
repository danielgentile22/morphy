import { test, expect } from '@playwright/test';

// Visual-regression baselines for the deterministic chrome (no live map
// canvas — that would be non-deterministic). Baselines are per-browser.

test('sidebar — Arkansas', async ({ page }) => {
  await page.goto('/?state=05');
  await expect(page.locator('h1')).toHaveText('Arkansas');
  await expect(page.getByTestId('top-list')).toBeVisible();
  await expect(page.locator('.sidebar')).toHaveScreenshot('sidebar-ar.png');
});

test('sidebar — Montana', async ({ page }) => {
  await page.goto('/?state=30');
  await expect(page.locator('h1')).toHaveText('Montana');
  await expect(page.getByTestId('top-list')).toBeVisible();
  await expect(page.locator('.sidebar')).toHaveScreenshot('sidebar-mt.png');
});

test('detail panel — parcel', async ({ page }) => {
  await page.goto('/?state=05');
  await page.locator('[data-testid="top-list"] button.row').first().click();
  const panel = page.getByTestId('details-panel');
  await expect(panel).toBeVisible();
  // Wait for the async full-row enrichment to settle so the transient
  // "Loading full details…" line isn't captured.
  await expect(page.getByTestId('enrich-loading')).toBeHidden();
  // The settled panel is pixel-content-identical to before this change, but
  // the transient enrich line's paint leaves WebKit's text anti-aliasing in
  // a slightly different sub-pixel state (~150 scattered px, varies per run).
  // A small tolerance absorbs that noise; a real layout/content regression
  // reflows thousands of pixels and still fails.
  await expect(panel).toHaveScreenshot('detail-parcel.png', { maxDiffPixels: 400 });
});
