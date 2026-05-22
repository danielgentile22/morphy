import { test, expect, type ConsoleMessage } from '@playwright/test';

/** Collect console errors + page errors for the zero-error gate. */
function watchConsole(page: import('@playwright/test').Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`);
  });
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

test('boots, renders the map, and lists AR + MT', async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto('/');

  // The map container and MapLibre canvas render.
  await expect(page.getByTestId('map')).toBeVisible();
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();

  // The state selector is catalog-driven: AR + MT, nothing hardcoded.
  const select = page.getByTestId('state-select');
  await expect(select).toBeVisible();
  await expect(select.locator('option')).toHaveCount(2);

  // Default state is the first alphabetically — Arkansas.
  await expect(page.locator('h1')).toHaveText('Arkansas');
  await expect(page.getByTestId('loading')).toBeHidden();

  expect(errors).toEqual([]);
});

test('switching state re-renders the chrome and updates the URL', async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto('/');
  await expect(page.locator('h1')).toHaveText('Arkansas');

  await page.getByTestId('state-select').selectOption('30');

  await expect(page.locator('h1')).toHaveText('Montana');
  await expect(page).toHaveURL(/[?&]state=30/);
  expect(errors).toEqual([]);
});

test('a deep-linked ?state= restores that state on load', async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto('/?state=30');
  await expect(page.locator('h1')).toHaveText('Montana');
  expect(errors).toEqual([]);
});

test('an unknown ?state= falls back to a real state with a notice', async ({ page }) => {
  await page.goto('/?state=99');
  await expect(page.locator('h1')).toHaveText('Arkansas');
  await expect(page.locator('.notice')).toContainText('99');
});
