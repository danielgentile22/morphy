import { test, expect } from '@playwright/test';

// Phase A performance budget. The rigorous budgets — parcel-tile paint
// (Phase B) and DuckDB filter latency (Phase C) — are asserted in those
// phases. Phase A's gate: the catalog-driven boot, which eager-loads the
// state's layer GeoJSON (~32 MB for AR), reaches an interactive map well
// within a usable window on the local server.
const BOOT_BUDGET_MS = 6000;

test('the app boots within the performance budget', async ({ page }) => {
  const started = Date.now();
  await page.goto('/?state=05');
  // "ready" — the catalog loaded, layers loaded, the top list rendered.
  await expect(page.getByTestId('top-list')).toBeVisible();
  await expect(page.getByTestId('loading')).toBeHidden();
  const elapsed = Date.now() - started;

  expect(elapsed, `boot took ${elapsed}ms (budget ${BOOT_BUDGET_MS}ms)`).toBeLessThan(
    BOOT_BUDGET_MS,
  );
});
