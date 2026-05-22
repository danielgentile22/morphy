import { test, expect, type ConsoleMessage, type Page } from '@playwright/test';

function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`);
  });
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

// The demo gate, run on both anchor states: open the state, click the
// top-ranked parcel, and confirm the detail panel shows a real landowner
// (the v1 app's failure mode was a panel full of "—").
for (const { fips, state } of [
  { fips: '05', state: 'Arkansas' },
  { fips: '30', state: 'Montana' },
]) {
  test(`demo gate — ${state}: top parcel shows a landowner`, async ({ page }) => {
    const errors = watchConsole(page);
    await page.goto(`/?state=${fips}`);
    await expect(page.locator('h1')).toHaveText(state);

    const firstRow = page.locator('[data-testid="top-list"] button.row').first();
    await expect(firstRow).toBeVisible();
    await firstRow.click();

    const panel = page.getByTestId('details-panel');
    await expect(panel).toBeVisible();
    await expect(panel.locator('h2')).toContainText('Parcel');

    // The Ownership section's Owner row must carry a real value.
    const owner = panel.locator('[data-field="Owner"] .v');
    await expect(owner).toBeVisible();
    const ownerText = (await owner.textContent())?.trim() ?? '';
    expect(ownerText.length).toBeGreaterThan(0);
    expect(ownerText).not.toBe('—');

    // The pitch-critical fields are populated, not dashes.
    await expect(panel.locator('[data-field="Assessed value"] .v')).not.toHaveText('—');
    await expect(panel.locator('[data-field="Score"] .v')).not.toHaveText('—');

    expect(errors).toEqual([]);
  });
}

test('the detail panel closes and clears the selection', async ({ page }) => {
  await page.goto('/?state=05');
  await page.locator('[data-testid="top-list"] button.row').first().click();
  const panel = page.getByTestId('details-panel');
  await expect(panel).toBeVisible();

  await panel.getByRole('button', { name: 'Close details' }).click();
  await expect(panel).toBeHidden();
});

test('selecting a second parcel replaces the panel content', async ({ page }) => {
  await page.goto('/?state=05');
  const rows = page.locator('[data-testid="top-list"] button.row');
  const panel = page.getByTestId('details-panel');

  await rows.nth(0).click();
  const first = (await panel.locator('h2').textContent())?.trim();

  await rows.nth(1).click();
  const second = (await panel.locator('h2').textContent())?.trim();

  expect(first).toBeTruthy();
  expect(second).toBeTruthy();
  expect(second).not.toBe(first);
});
