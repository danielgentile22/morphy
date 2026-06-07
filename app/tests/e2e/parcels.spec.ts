import { test, expect, type ConsoleMessage, type Page } from '@playwright/test';

// Phase B — the PMTiles parcel base layer + the county choropleth.
// The map is exposed on window.__pilotMap; evaluate callbacks run in the
// browser, so `any` for that handle is glue.
//
// Timing is measured *in-page* (MapLibre's own events / a setTimeout
// poll). Playwright's rAF-polled waitForFunction is starved while the
// main thread processes the eager GeoJSON at load, which would inflate a
// measurement by ~10 s even though paint is sub-second.

function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (m: ConsoleMessage) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`);
  });
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  return errors;
}

/** Wait — in-page — until the map exists, has the parcel source, and has
 *  fully settled (initial tiles loaded + rendered). */
async function waitForMapReady(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve, reject) => {
        const deadline = Date.now() + 30_000;
        const tick = (): void => {
          const m = (window as any).__pilotMap;
          if (m && m.isStyleLoaded() && m.getSource('src:parcels') && m.loaded()) resolve();
          else if (Date.now() > deadline) reject(new Error('map not ready within 30s'));
          else setTimeout(tick, 100);
        };
        tick();
      }),
  );
}

/** Jump (no animation) and resolve with the ms until the map next idles. */
async function jumpAndSettle(
  page: Page,
  center: [number, number],
  zoom: number,
): Promise<number> {
  return page.evaluate(
    ([c, z]) =>
      new Promise<number>((resolve) => {
        const m = (window as any).__pilotMap;
        const start = performance.now();
        m.once('idle', () => resolve(performance.now() - start));
        m.jumpTo({ center: c, zoom: z });
      }),
    [center, zoom] as const,
  );
}

async function parcelFeatureCount(page: Page): Promise<number> {
  return page.evaluate(
    () => (window as any).__pilotMap.queryRenderedFeatures({ layers: ['parcels:fill'] }).length,
  );
}

// Little Rock, AR — parcel-dense.
const AR_PARCEL_AREA: [number, number] = [-92.289, 34.746];

test('parcels render from the PMTiles vector source', async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto('/?state=05#/explore');
  await waitForMapReady(page);

  // The pmtiles source + parcel fill layer were added by convention.
  expect(
    await page.evaluate(() => {
      const m = (window as any).__pilotMap;
      return !!m.getSource('src:parcels') && !!m.getLayer('parcels:fill');
    }),
  ).toBe(true);

  await jumpAndSettle(page, AR_PARCEL_AREA, 13);
  expect(await parcelFeatureCount(page)).toBeGreaterThan(0);
  expect(errors).toEqual([]);
});

test('time-to-first-parcel-paint is within the 1.5 s budget', async ({ page }) => {
  await page.goto('/?state=05#/explore');
  await waitForMapReady(page);

  // Median of several first-paints (each jumps in from a low zoom) — the
  // plan's budgets are medians, and a median is robust to a transient CPU
  // spike from other tests running in parallel.
  const samples: number[] = [];
  for (let i = 0; i < 3; i++) {
    await jumpAndSettle(page, AR_PARCEL_AREA, 7);
    samples.push(await jumpAndSettle(page, AR_PARCEL_AREA, 13));
  }
  samples.sort((a, b) => a - b);
  const median = Math.round(samples[1]);
  expect(
    median,
    `parcel-paint median ${median}ms of ${samples.map(Math.round)} (budget 1500ms)`,
  ).toBeLessThanOrEqual(1500);
});

test('clicking a parcel opens a parcel detail panel', async ({ page }) => {
  await page.goto('/?state=05#/explore');
  await waitForMapReady(page);

  // Isolate the parcel base layer so the click lands on it (towers is the
  // only overlay over parcels now — distress/views were retired, round 3).
  await page.getByTestId('layer-toggle-towers').click();
  await jumpAndSettle(page, AR_PARCEL_AREA, 13);
  expect(await parcelFeatureCount(page)).toBeGreaterThan(0);

  const box = (await page.getByTestId('map').boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);

  const panel = page.getByTestId('details-panel');
  await expect(panel).toBeVisible();
  await expect(panel.locator('.kind')).toHaveText('parcel');
  await expect(panel.locator('[data-field="Owner"] .v')).toBeVisible();
});

// The county distress choropleth was retired in UI overhaul round 3 — distress
// is now a top-bar filter field, not a coloured map overlay. (Former test:
// "the county choropleth renders and a county opens a panel".)

test('panning and zooming the parcels emits no errors; tiles return 200/206', async ({ page }) => {
  const errors = watchConsole(page);
  const tileStatuses: number[] = [];
  page.on('response', (r) => {
    if (r.url().includes('parcels.pmtiles')) tileStatuses.push(r.status());
  });

  await page.goto('/?state=05#/explore');
  await waitForMapReady(page);

  for (const z of [11, 13, 12, 14, 10]) {
    await jumpAndSettle(page, AR_PARCEL_AREA, z);
  }

  expect(errors).toEqual([]);
  expect(tileStatuses.length, 'pmtiles range requests were made').toBeGreaterThan(0);
  for (const status of tileStatuses) {
    expect([200, 206]).toContain(status);
  }
});
