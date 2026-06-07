import { test, expect, type ConsoleMessage, type Page } from '@playwright/test';

// The map is exposed on window.__pilotMap as a test handle; the evaluate
// callbacks below run in the browser context, so `any` for that handle is glue.

function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`);
  });
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

/** Wait until the map exists, its style is loaded, and syncLayers has run. */
async function waitForLayers(page: Page): Promise<void> {
  await page.waitForFunction(
    () => {
      const m = (window as any).__pilotMap;
      return !!m && m.isStyleLoaded() && !!m.getSource('src:towers');
    },
    undefined,
    { timeout: 20_000 },
  );
}

/** True if any MapLibre sublayer of a logical layer is visible. */
async function logicalLayerVisible(page: Page, name: string): Promise<boolean> {
  return page.evaluate((n) => {
    const m = (window as any).__pilotMap;
    if (!m) return false;
    const layers = m.getStyle().layers.filter((l: { id: string }) => l.id.startsWith(`${n}:`));
    if (layers.length === 0) return false;
    return layers.some(
      (l: { id: string }) => (m.getLayoutProperty(l.id, 'visibility') ?? 'visible') !== 'none',
    );
  }, name);
}

async function sourceExists(page: Page, sourceId: string): Promise<boolean> {
  return page.evaluate((id) => !!(window as any).__pilotMap?.getSource(id), sourceId);
}

test('layer toggles show and hide map layers, no console errors', async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto('/?state=05#/explore');
  await waitForLayers(page);

  expect(await logicalLayerVisible(page, 'towers')).toBe(true);

  await page.getByTestId('layer-toggle-towers').click();
  await expect.poll(() => logicalLayerVisible(page, 'towers')).toBe(false);

  await page.getByTestId('layer-toggle-towers').click();
  await expect.poll(() => logicalLayerVisible(page, 'towers')).toBe(true);

  // Solar is off by default; toggling it on renders it.
  expect(await logicalLayerVisible(page, 'solar_facilities')).toBe(false);
  await page.getByTestId('layer-toggle-solar_facilities').click();
  await expect.poll(() => logicalLayerVisible(page, 'solar_facilities')).toBe(true);

  expect(errors).toEqual([]);
});

test('toggling a heavy view lazy-loads its GeoJSON', async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto('/?state=05#/explore');
  await waitForLayers(page);

  // llc_owned_parcels_with_infra is a heavy view — not loaded until toggled.
  const toggle = page.getByTestId('layer-toggle-llc_owned_parcels_with_infra');
  await expect(toggle).toBeVisible();
  expect(await sourceExists(page, 'src:llc_owned_parcels_with_infra')).toBe(false);

  await toggle.click();
  await expect
    .poll(() => sourceExists(page, 'src:llc_owned_parcels_with_infra'), { timeout: 20_000 })
    .toBe(true);
  await expect(toggle).toBeChecked();

  expect(errors).toEqual([]);
});

test('the owner filter narrows the top list', async ({ page }) => {
  await page.goto('/?state=05#/explore');
  const count = page.getByTestId('top-count');
  await expect(count).toContainText('Showing 1,000 of 1,000');

  await page.getByTestId('owner-filter').fill('trust');
  await expect(count).not.toContainText('Showing 1,000 of 1,000');

  const shown = Number(
    (await count.textContent())!.match(/Showing ([\d,]+)/)![1].replace(/,/g, ''),
  );
  expect(shown).toBeGreaterThan(0);
  expect(shown).toBeLessThan(1000);

  await page.getByTestId('owner-filter').fill('');
  await expect(count).toContainText('Showing 1,000 of 1,000');
});

test('owner-kind chips filter the top list', async ({ page }) => {
  await page.goto('/?state=05#/explore');
  const count = page.getByTestId('top-count');

  await page.getByRole('button', { name: 'LLC', exact: true }).click();
  const shown = Number(
    (await count.textContent())!.match(/Showing ([\d,]+)/)![1].replace(/,/g, ''),
  );
  expect(shown).toBeGreaterThan(0);
  expect(shown).toBeLessThan(1000);

  await page.getByRole('button', { name: 'All', exact: true }).click();
  await expect(count).toContainText('Showing 1,000 of 1,000');
});

test('the summary card renders', async ({ page }) => {
  await page.goto('/?state=05#/explore');
  await expect(page.getByTestId('summary-card')).toContainText('2,116,976');
});

test('every layer toggle works without errors', async ({ page }) => {
  // UI overhaul round 3: the panel is towers + solar only (parcels are an
  // always-on base layer, distress is a filter field, views were retired).
  const pageErrors: string[] = [];
  page.on('pageerror', (e) => pageErrors.push(e.message));
  await page.goto('/?state=05#/explore');
  await waitForLayers(page);

  const toggles = page.locator('[data-testid^="layer-toggle-"]');
  const n = await toggles.count();
  expect(n, 'towers + solar layer toggles').toBe(2);

  for (let i = 0; i < n; i++) {
    const t = toggles.nth(i);
    const before = await t.isChecked();
    await t.click();
    await expect(t).toBeEnabled();
    expect(await t.isChecked()).toBe(!before);
  }
  expect(pageErrors).toEqual([]);
});

/** Project a source's first feature to a viewport pixel (Point or Polygon). */
async function featurePoint(page: Page, sourceId: string): Promise<{ x: number; y: number }> {
  await page.waitForFunction(
    (id) => {
      const m = (window as any).__pilotMap;
      return m && m.isSourceLoaded(id) && m.querySourceFeatures(id).length > 0;
    },
    sourceId,
    { timeout: 20_000 },
  );
  const pt = await page.evaluate((id) => {
    const m = (window as any).__pilotMap;
    const feats = m.querySourceFeatures(id);
    const g = feats[0]?.geometry;
    if (!g) return null;
    let coord: [number, number] | undefined;
    if (g.type === 'Point') coord = g.coordinates;
    else {
      const ring = g.type === 'MultiPolygon' ? g.coordinates[0][0] : g.coordinates[0];
      const n = ring.length;
      coord = [
        ring.reduce((s: number, c: number[]) => s + c[0], 0) / n,
        ring.reduce((s: number, c: number[]) => s + c[1], 0) / n,
      ];
    }
    const p = m.project(coord);
    const r = m.getContainer().getBoundingClientRect();
    return { x: r.left + p.x, y: r.top + p.y };
  }, sourceId);
  if (!pt) throw new Error(`no feature found in ${sourceId}`);
  return pt;
}

test('clicking a solar facility opens a solar detail panel', async ({ page }) => {
  await page.goto('/?state=05#/explore');
  await waitForLayers(page);

  // Isolate solar so the click lands on it, not an overlapping layer.
  await page.getByTestId('layer-toggle-towers').click();
  await page.getByTestId('layer-toggle-solar_facilities').click();

  const pt = await featurePoint(page, 'src:solar_facilities');
  await page.mouse.click(pt.x, pt.y);

  const panel = page.getByTestId('details-panel');
  await expect(panel).toBeVisible();
  await expect(panel.locator('.kind')).toHaveText('solar');
});

test('clicking a tower on the map opens a tower detail panel', async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto('/?state=05#/explore');
  await waitForLayers(page);

  // Wait for the towers source to finish loading, then project a real
  // tower's coordinates to a viewport pixel and click it.
  await page.waitForFunction(
    () => {
      const m = (window as any).__pilotMap;
      return m && m.isSourceLoaded('src:towers') && m.querySourceFeatures('src:towers').length > 0;
    },
    undefined,
    { timeout: 20_000 },
  );

  const pt = await page.evaluate(() => {
    const m = (window as any).__pilotMap;
    const feats = m
      .querySourceFeatures('src:towers')
      .filter((f: any) => f.geometry?.type === 'Point');
    if (feats.length === 0) return null;
    const p = m.project(feats[0].geometry.coordinates);
    const r = m.getContainer().getBoundingClientRect();
    return { x: r.left + p.x, y: r.top + p.y };
  });
  expect(pt, 'a tower feature was found to click').not.toBeNull();

  await page.mouse.click(pt!.x, pt!.y);

  const panel = page.getByTestId('details-panel');
  await expect(panel).toBeVisible();
  await expect(panel.locator('.kind')).toHaveText('tower');
  expect(errors).toEqual([]);
});
