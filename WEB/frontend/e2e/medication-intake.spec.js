import { test, expect } from '@playwright/test';

/**
 * The "I take X" flow, end to end: real browser → the real production build →
 * the real backend → the real database → RxNorm.
 *
 * Nothing about medications is mocked. The point is to prove the screen works
 * against the actual API rather than against a fixture that agrees with it,
 * and unit tests cannot do that — they assert on a mock of the response shape,
 * which is exactly the thing that drifts.
 *
 * Requires the dev stack up and scripts/make_proof_user.py to have seeded the
 * account (direct registration is closed in dev).
 */

const EMAIL = 'uiproof@example.com';
const PASSWORD = 'ProofPassw0rd!23';

/**
 * Sign in ONCE for the whole file.
 *
 * /auth/login is rate limited (RATE_LIMIT_AUTH), and logging in per test trips
 * it — the run then fails in a way that looks like a broken feature rather than
 * a throttled one. One token, reused.
 */
let sharedToken = null;

test.beforeAll(async ({ playwright }) => {
  const api = await playwright.request.newContext({
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://frontend-preview:5173',
  });
  await api.get('/api/v1/auth/csrf-cookie');
  const csrf = (await api.storageState()).cookies
    .find((c) => c.name === 'csrf_token')?.value || '';

  const res = await api.post('/api/v1/auth/login', {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-CSRF-Token': csrf,
    },
    data: `username=${encodeURIComponent(EMAIL)}&password=${encodeURIComponent(PASSWORD)}`,
  });
  expect(res.status(), await res.text()).toBe(200);
  sharedToken = (await res.json()).access_token;
  expect(sharedToken).toBeTruthy();
  await api.dispose();
});

async function signInForReal(page) {
  await page.goto('/login');
  await page.evaluate((t) => localStorage.setItem('token', t), sharedToken);
}

test.describe('Medication intake, against the real backend', () => {
  test('reads "I take Calcitriol" and proposes the dose from history', async ({ page }) => {
    await signInForReal(page);
    await page.goto('/medications');

    const panel = page.getByTestId('intake-intent');
    await expect(panel).toBeVisible();

    await panel.getByPlaceholder(/I take Calcitriol/i).fill('I take Calcitriol');
    await panel.getByRole('button', { name: /read this/i }).click();

    const proposal = page.getByTestId('intake-proposal');
    await expect(proposal).toBeVisible({ timeout: 20_000 });
    await expect(proposal).toContainText(/Calcitriol/i);
    // The dose came from this account's own logs, and the screen says so.
    await expect(proposal).toContainText(/mcg/);
    await expect(proposal).toContainText(/your last \d+ dose/i);
  });

  test('accepting the proposal fills the form and logs nothing by itself', async ({ page }) => {
    await signInForReal(page);
    await page.goto('/medications');

    const panel = page.getByTestId('intake-intent');
    await panel.getByPlaceholder(/I take Calcitriol/i).fill('I take Calcitriol');
    await panel.getByRole('button', { name: /read this/i }).click();
    await expect(page.getByTestId('intake-proposal')).toBeVisible({ timeout: 20_000 });

    // No write happens on accept — it only fills the form the user already knows.
    let wrote = false;
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes('/medications/dose-logs')) wrote = true;
    });

    await page.getByRole('button', { name: /use this/i }).click();
    // The <datalist> this used to query is gone — it was replaced by a real
    // combobox (MedicationPicker) because datalist matching differs between
    // browsers, cannot show provenance, and is unreliable on mobile. The spec
    // kept asserting on the old selector and so could only ever fail.
    await expect(page.getByTestId('medication-picker-input')).toHaveValue(/Calcitriol/i);
    expect(wrote).toBe(false);
  });

  test('a stopped 2017 prescription is never offered as a current option', async ({ page }) => {
    await signInForReal(page);
    await page.goto('/medications');
    await expect(page.getByTestId('intake-intent')).toBeVisible();

    // This asserted on `#med-catalog option` — a <datalist> that no longer
    // exists. `allTextContents()` returned [], the loop body never ran, and the
    // test PASSED having checked nothing, while the picker it guards is a
    // safety control: a stopped 2017 prescription must never be offered as
    // "what am I taking today".
    const picker = page.getByTestId('medication-picker-input');
    await picker.click();
    await picker.fill('i');

    const list = page.getByTestId('medication-suggestions');
    await expect(list).toBeVisible({ timeout: 10_000 });

    const offered = await list.getByRole('option').allTextContents();
    // Refuse to be vacuous: an empty list would pass the check below trivially,
    // which is exactly how this test hid for so long.
    expect(offered.length).toBeGreaterThan(0);
    for (const name of offered) {
      expect(name).not.toMatch(/Meperidine|Ibuprofen 200 MG/i);
    }
  });
});
