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
  await expect(panel).toHaveScreenshot('detail-parcel.png');
});
