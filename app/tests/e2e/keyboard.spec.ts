import { test, expect, type Page } from '@playwright/test';

// Phase D — keyboard shortcuts: ? help, Esc clear selection, f focus search.

async function waitReady(page: Page): Promise<void> {
  await page.getByTestId('top-list').waitFor({ state: 'visible', timeout: 25_000 });
}

test('? toggles the help overlay', async ({ page }) => {
  await page.goto('/?state=05#/explore');
  await waitReady(page);

  const help = page.getByTestId('help');
  await expect(help).toBeHidden();
  await page.keyboard.press('?');
  await expect(help).toBeVisible();
  await page.keyboard.press('?');
  await expect(help).toBeHidden();
});

test('Esc closes the help overlay, then clears the selection', async ({ page }) => {
  await page.goto('/?state=05#/explore');
  await waitReady(page);

  await page.locator('[data-testid="top-list"] button.row').first().click();
  const panel = page.getByTestId('details-panel');
  await expect(panel).toBeVisible();

  // Esc first dismisses help if open...
  await page.keyboard.press('?');
  await expect(page.getByTestId('help')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('help')).toBeHidden();
  await expect(panel).toBeVisible();

  // ...then clears the selection.
  await page.keyboard.press('Escape');
  await expect(panel).toBeHidden();
});

test('f focuses the owner search', async ({ page }) => {
  await page.goto('/?state=05#/explore');
  await waitReady(page);

  await page.keyboard.press('f');
  await expect(page.getByTestId('owner-search')).toBeFocused();
});
