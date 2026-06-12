import { test, expect, type Page } from '@playwright/test';

// Slice A (#28) — carriers render on the surface a clicked tower lands on:
// the LeadPage holdings (`#/lead/:key`). That surface is backend-served, and
// the E2E harness deliberately does NOT boot the Lead backend (only the static
// /data server + vite preview). So we drive the real LeadPage → CarrierList
// rendering path with a seeded session + a mocked `/api/leads/:id` — exercising
// the component, badges, tooltips, and empty state end-to-end in the browser.

const CID = 'natcarrier01';

const LEAD = {
  owner: {
    display_cluster_id: CID,
    owner_name: 'CARRIER TEST OWNER',
    owner_kind: 'llc',
    states: ['AR'],
    n_states: 1,
    cross_state: false,
    parcel_count: 2,
    tower_count: 2,
    solar_count: 0,
    total_assessed_value: 123456,
    max_parcel_score: 0.9,
    score: 0.95,
    distress_tier: 'distressed',
    in_oz: true,
    in_qct: false,
    persistent_poverty: false,
    status: 'new',
    counties: ['05001'],
    structure_count: 2,
    structure_types: ['tower'],
    active_tower_count: 2,
    tallest_tower_height_m: 120,
  },
  status: 'new',
  notes: '',
  updated_at: null,
  attempts: [],
  contact_name: '',
  contact_phone: '',
  contact_email: '',
  best_channel: '',
  mailing_address: null,
  tallest_tower_height_m: 120,
  merged_members: [],
  holdings: [
    {
      parcel_id: 'P-WITH-CARRIERS',
      state: 'AR',
      county_fips: '05001',
      land_use: 'AV',
      assessed_value: 100000,
      acreage: 10,
      tower_count: 1,
      solar_count: 0,
      bbox: [-91.35, 32.95, -91.25, 33.05],
      point: [-91.3, 33.0],
      structures: [
        {
          type: 'tower',
          asr: '1029901',
          height_m: 120,
          lat: 33.0,
          lon: -91.3,
          active: true,
          structure_kind: 'TOWER',
          carriers: [
            { carrier_name: 'AT&T', callsign: 'KNKN544', license_expiry: '2031-10-01', confidence_tag: 'verified' },
            { carrier_name: 'ALLTEL Corporation', callsign: 'WPOI253', license_expiry: '2009-01-25', confidence_tag: 'likely' },
            { carrier_name: 'Rural Cellular', callsign: 'WQAA111', license_expiry: null, confidence_tag: 'possible' },
          ],
        },
      ],
    },
    {
      parcel_id: 'P-NO-CARRIERS',
      state: 'AR',
      county_fips: '05001',
      land_use: 'AV',
      assessed_value: 23456,
      acreage: 5,
      tower_count: 1,
      solar_count: 0,
      bbox: [-91.15, 33.05, -91.05, 33.15],
      point: [-91.1, 33.1],
      structures: [
        {
          type: 'tower',
          asr: '0809460',
          height_m: 60,
          lat: 33.1,
          lon: -91.1,
          active: true,
          structure_kind: 'TOWER',
          carriers: [],
        },
      ],
    },
  ],
};

/** Seed a signed-in session + mock the Lead backend the harness doesn't run.
 *  Auth rides in an httpOnly cookie (PRD #130) the SPA can't read — mocking
 *  /api/auth/me to succeed IS a signed-in session as far as the app knows. */
async function primeLeadBackend(page: Page): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/auth/me')) {
      return route.fulfill({ json: { tenant_id: 1, email: 'e2e@example.com' } });
    }
    if (url.includes('/api/counts')) {
      return route.fulfill({ json: { candidates: 1, my_leads: 0 } });
    }
    if (url.includes('/api/candidates')) {
      return route.fulfill({ json: { count: 0, candidates: [] } });
    }
    if (url.includes('/api/my-leads')) {
      return route.fulfill({ json: { count: 0, leads: [] } });
    }
    if (url.includes('/api/leads/')) {
      return route.fulfill({ json: LEAD });
    }
    return route.fulfill({ json: {} });
  });
}

test('LeadPage renders carriers with confidence badges + tooltips', async ({ page }) => {
  await primeLeadBackend(page);
  await page.goto(`/#/lead/${CID}`);

  // The lead loaded (holdings, not the sign-in or error state).
  await expect(page.getByTestId('lead-page')).toBeVisible();
  await expect(page.getByTestId('holdings')).toBeVisible();

  // Two tower rows ⇒ two carrier lists (one populated, one empty).
  const lists = page.getByTestId('carrier-list');
  await expect(lists).toHaveCount(2);

  // The populated tower shows the licensee + a verified badge.
  await expect(page.getByText('AT&T').first()).toBeVisible();
  const verified = page.locator('[data-confidence="verified"]').first();
  await expect(verified).toBeVisible();
  await expect(verified).toHaveText('Verified');
  // Tooltip + accessible label explain the tag (colour is never the only cue).
  await expect(verified).toHaveAttribute('title', /ASR-number/i);
  await expect(verified).toHaveAttribute('aria-label', /Verified/);

  // All three confidence tiers render their badge.
  await expect(page.locator('[data-confidence="likely"]').first()).toHaveText('Likely');
  await expect(page.locator('[data-confidence="possible"]').first()).toHaveText('Possible');
});

test('LeadPage shows the empty state for a tower with no carriers', async ({ page }) => {
  await primeLeadBackend(page);
  await page.goto(`/#/lead/${CID}`);

  await expect(page.getByTestId('lead-page')).toBeVisible();
  // The no-carrier tower reads as normal (it is the common case), not an error.
  await expect(page.getByText('No carriers identified').first()).toBeVisible();
});
