import { test, expect, type Page } from '@playwright/test';

// Phase C — the DuckDB-WASM query engine, exercised directly via the
// window.__duckDb test handle against the real parcels_attr.parquet.

/** Wait until the app is ready (so the store has pointed the engine at
 *  the state's parquet) and the engine handle exists. */
async function waitForEngine(page: Page): Promise<void> {
  await page.getByTestId('summary-card').waitFor({ state: 'visible', timeout: 25_000 });
  await page.waitForFunction(() => !!(window as any).__duckDb, undefined, { timeout: 20_000 });
}

test('DuckDB-WASM counts every AR parcel', async ({ page }) => {
  await page.goto('/?state=05');
  await waitForEngine(page);
  const total = await page.evaluate(() => (window as any).__duckDb.count(''));
  // AR has 2,116,976 parcels (catalog.json).
  expect(total).toBe(2116976);
});

test('a WHERE clause narrows the count', async ({ page }) => {
  await page.goto('/?state=05');
  await waitForEngine(page);
  const result = await page.evaluate(async () => {
    const db = (window as any).__duckDb;
    const all = await db.count('');
    const llc = await db.count("owner_kind IN ('llc')");
    const distressedLlc = await db.count("owner_kind IN ('llc') AND distress_tier IN ('distressed')");
    return { all, llc, distressedLlc };
  });
  expect(result.llc).toBeGreaterThan(0);
  expect(result.llc).toBeLessThan(result.all);
  expect(result.distressedLlc).toBeGreaterThan(0);
  expect(result.distressedLlc).toBeLessThanOrEqual(result.llc);
});

test('matchingIds and a parcel row fetch work', async ({ page }) => {
  await page.goto('/?state=05');
  await waitForEngine(page);
  const out = await page.evaluate(async () => {
    const db = (window as any).__duckDb;
    const ids: string[] = await db.matchingIds('has_tower', 50);
    const row = ids.length ? await db.fetchParcel(ids[0]) : null;
    return { count: ids.length, firstId: ids[0], row };
  });
  expect(out.count).toBeGreaterThan(0);
  expect(out.count).toBeLessThanOrEqual(50);
  expect(out.row).not.toBeNull();
  expect(out.row.parcel_id).toBe(out.firstId);
  // The slim parquet keeps the JSON-string nested columns.
  expect(out.row).toHaveProperty('distress_overlays');
  expect(out.row).not.toHaveProperty('geometry');
});

test('a 3-filter compound query is within the 500 ms median budget', async ({ page }) => {
  await page.goto('/?state=05');
  await waitForEngine(page);
  // Warm the engine, then measure the median of repeated compound queries.
  const median = await page.evaluate(async () => {
    const db = (window as any).__duckDb;
    const where =
      "owner_kind IN ('llc','trust') AND distress_tier IN ('distressed') AND has_tower";
    await db.count(where); // warm-up
    const samples: number[] = [];
    for (let i = 0; i < 5; i++) {
      const t = performance.now();
      await db.count(where);
      samples.push(performance.now() - t);
    }
    samples.sort((a, b) => a - b);
    return samples[2];
  });
  expect(Math.round(median), `3-filter query median ${Math.round(median)}ms`).toBeLessThan(500);
});
