import { test, expect } from '@playwright/test';
import { mockAppChrome, signIn as authenticate } from './helpers.js';

// Conditions are a cornerstone of the record, and the web screen shipped
// unreachable for the app's whole history — no route, no link (CONDITIONS.md
// §0). These specs exist so that cannot happen again silently.

const ESRD = {
  id: 1,
  condition_name: 'End-Stage Renal Disease',
  category: 'renal',
  severity: 'severe',
  is_active: true,
  icd10_code: 'N18.6',
  icd11_code: 'GB61.5',
  icd11_title: 'Chronic kidney disease, stage 5',
};

const SICKLE = {
  id: 2,
  condition_name: 'Sickle cell disease',
  category: 'blood_disorder',
  severity: 'moderate',
  is_active: true,
  icd10_code: null,
  icd11_code: '3A51.1',
  icd11_title: 'Sickle cell disease without crisis',
};

async function signIn(page, { conditions = [ESRD, SICKLE], failConditions = false } = {}) {
  // Without this the app's chrome endpoints 401, the interceptor decides the
  // session is dead, and the page redirects to /login mid-assertion.
  await mockAppChrome(page);
  await page.route('**/api/v1/chronic/icd11/search**', (r) =>
    r.fulfill({
      body: JSON.stringify({
        query: 'ESRD',
        total: 1,
        catalog_version: 'ICD-11 MMS 2025-01',
        results: [
          {
            code: 'GB61.5',
            title: 'Chronic kidney disease, stage 5',
            chapter: '16',
            chapter_title: 'Diseases of the genitourinary system',
            is_leaf: true,
            is_residual: false,
          },
        ],
      }),
      headers: { 'Content-Type': 'application/json' },
    })
  );
  await page.route('**/api/v1/chronic/conditions**', (r) =>
    failConditions
      ? r.fulfill({ status: 500, body: '{"detail":"boom"}', headers: { 'Content-Type': 'application/json' } })
      : r.fulfill({
          body: JSON.stringify(conditions),
          headers: { 'Content-Type': 'application/json' },
        })
  );

  await authenticate(page);
}

test.describe('Conditions', () => {
  test('the route is reachable and lists every condition', async ({ page }) => {
    await signIn(page);
    await page.goto('/chronic-conditions');

    // A patient holds many conditions — one row each, independently coded.
    // By heading: the plain text also appears inside the ICD-11 title line
    // ("Sickle cell disease without crisis"), which is itself the proof that
    // the official WHO label is rendered alongside the code.
    await expect(page.getByRole('heading', { name: /End-Stage Renal Disease/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Sickle cell disease/ })).toBeVisible();
    await expect(page.getByText('Sickle cell disease without crisis')).toBeVisible();
    await expect(page.getByText(/ICD-11: GB61\.5/)).toBeVisible();
    await expect(page.getByText(/ICD-10: N18\.6/)).toBeVisible();
  });

  test('is reachable from Profile', async ({ page }) => {
    await signIn(page);
    await page.goto('/profile');

    const link = page.getByTestId('profile-conditions-link');
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/chronic-conditions/);
  });

  test('the ICD-11 picker resolves a lay abbreviation', async ({ page }) => {
    await signIn(page);
    await page.goto('/chronic-conditions');

    await page.getByRole('button', { name: /Add Condition/i }).first().click();
    const search = page.getByRole('combobox', { name: 'ICD-11 Code' });
    await expect(search).toBeVisible();

    await search.fill('ESRD');
    await page.getByRole('option', { name: /Chronic kidney disease, stage 5/ }).click();
    await expect(page.getByTestId('icd11-selected')).toContainText('GB61.5');
  });

  test('a failed load is an error, not an empty list', async ({ page }) => {
    await signIn(page, { failConditions: true });
    await page.goto('/chronic-conditions');

    await expect(page.getByTestId('conditions-load-error')).toBeVisible();
    await expect(page.getByText(/No chronic conditions recorded yet/)).toHaveCount(0);
  });
});
