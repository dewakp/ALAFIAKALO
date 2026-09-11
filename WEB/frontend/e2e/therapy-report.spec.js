import { expect, test } from '@playwright/test';
import { mockAppChrome, signIn } from './helpers.js';

/**
 * The printable treatment report.
 *
 * NOTE the mocked path: the router mounts at `/chronic`, not
 * `/chronic-conditions`. The first version of this spec mocked the latter and
 * passed — against a route that does not exist — which proved nothing about
 * the real endpoint. A mock is only evidence if it matches the wire.
 *
 * Asserts the things that would silently mislead a clinician on paper: that a
 * recorded value is not printed as "not recorded", that the two time figures
 * stay apart, and that an absent thrill shouts rather than looking like an
 * empty box.
 */
const json = (body, status = 200) => ({
  status, body: JSON.stringify(body),
  headers: { 'Content-Type': 'application/json' },
});

const SESSION = {
  id: 42,
  session_number: 7,
  scheduled_date: '2026-09-01T00:00:00',
  facility_name: 'Victoria Island Dialysis',
  attending_physician: 'Dr. A. Balogun',
  actual_start_time: '2026-09-01T08:00:00Z',
  actual_end_time: '2026-09-01T12:00:00Z',   // 240 min on the clock
  machine_total_time_minutes: 228,            // 12 min not dialysing
  dialysis_access_type: 'AV Fistula',
  access_thrill_bruit: true,
  post_access_thrill_bruit: false,            // ABSENT — must shout
  alarm_test_completed: true,
  pre_dialysis_weight_kg: 72.4,
  post_dialysis_weight_kg: 70.1,
  fluid_removed_ml: 2300,                     // scale-derived, already net
  saline_added_ml: 250,
  total_uf_liters: 2.55,                      // machine gross
  drugs_administered: 'Epoetin alfa 4000 units',
};

test.beforeEach(async ({ page }) => {
  await mockAppChrome(page);
  // The report lives inside the authenticated layout, so an unsigned spec is
  // redirected to /login and every assertion fails on a page that never
  // rendered — which looks like the report being broken.
  await signIn(page);
  await page.route('**/api/v1/chronic/therapy-sessions/42', (r) =>
    r.fulfill(json(SESSION)));
});

test('a recorded value never prints as not-recorded', async ({ page }) => {
  await page.goto('/therapy-report/42');
  await expect(page.getByText('Victoria Island Dialysis')).toBeVisible();
  await expect(page.getByText('Dr. A. Balogun')).toBeVisible();
  await expect(page.getByText('250 mL')).toBeVisible();
});

test('clock time and machine time are printed as two different numbers', async ({ page }) => {
  await page.goto('/therapy-report/42');
  // end - start = 240; the machine reports 228. Conflating them overstates the
  // dose delivered, because Kt/V follows time actually ON dialysis.
  await expect(page.getByText('240 min')).toBeVisible();
  await expect(page.getByText('228 min')).toBeVisible();
});

test('saline is deducted from the MACHINE figure, not the scale figure', async ({ page }) => {
  await page.goto('/therapy-report/42');
  // 2.55 L gross − 250 mL saline = 2300 mL, which AGREES with the scale's
  // 2300 mL — so the figure appears twice, and that agreement is the point.
  // Scoped to the row, because an unscoped getByText matches both.
  const net = page.locator('.tr-row', { hasText: 'Net from machine' });
  await expect(net).toContainText('2300 mL');

  // Deducting from the scale figure instead would print 2050 and count the
  // same 250 mL twice — the patient was already weighed after the saline.
  await expect(page.getByText('2050 mL')).toHaveCount(0);
});

test('an absent thrill shouts instead of looking like an empty box', async ({ page }) => {
  await page.goto('/therapy-report/42');
  await expect(page.getByText('ABSENT — urgent')).toBeVisible();
  await expect(page.getByText('Present (normal)')).toBeVisible();
});

test('a failed load says so rather than printing a blank report', async ({ page }) => {
  await page.route('**/api/v1/chronic/therapy-sessions/42', (r) =>
    r.fulfill(json({ detail: 'nope' }, 500)));
  await page.goto('/therapy-report/42');
  await expect(page.getByRole('alert')).toBeVisible();
  // Empty fields on a clinical report read as findings. Nothing must render.
  await expect(page.getByText('Weights')).toHaveCount(0);
});
