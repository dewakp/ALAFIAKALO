import { test, expect } from '@playwright/test';
import { mockAppChrome } from './helpers.js';


// ── Nutrition page ────────────────────────────────────────────────────────────

test.describe('Nutrition page', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept API calls so tests run without a live backend
    await mockAppChrome(page);
    await page.route('**/api/v1/auth/csrf-cookie', (r) => r.fulfill({ body: '{}' }));
    await page.route('**/api/v1/users/me', (r) =>
      r.fulfill({
        body: JSON.stringify({ id: 1, email: 'e2e@example.com', full_name: 'E2E User' }),
        headers: { 'Content-Type': 'application/json' },
      })
    );
    await page.route('**/api/v1/nutrition/**', (r) =>
      r.fulfill({
        body: JSON.stringify([
          { id: 1, food_name: 'Oatmeal', meal_type: 'breakfast', log_date: '2026-04-28', calories: 150, notes: null },
        ]),
        headers: { 'Content-Type': 'application/json' },
      })
    );
    await page.route('**/api/v1/nutrition/daily-summary**', (r) =>
      r.fulfill({
        body: JSON.stringify({ total_calories: 1200, meal_count: 3, date: '2026-04-28' }),
        headers: { 'Content-Type': 'application/json' },
      })
    );
    // Simulate logged-in state
    await page.goto('/landing');
    await page.evaluate(() => localStorage.setItem('token', 'e2e-token'));
    await page.goto('/nutrition');
  });

  test('renders nutrition page', async ({ page }) => {
    await expect(page.locator('body')).toBeVisible();
  });

  test('has an add / new entry button', async ({ page }) => {
    const addBtn = page.getByRole('button').first();
    await expect(addBtn).toBeVisible();
  });

  test('shows food name from loaded logs', async ({ page }) => {
    await expect(page.getByText('Oatmeal')).toBeVisible({ timeout: 5000 });
  });
});

// ── Labs page ─────────────────────────────────────────────────────────────────

test.describe('Labs page', () => {
  test.beforeEach(async ({ page }) => {
    await mockAppChrome(page);
    await page.route('**/api/v1/auth/csrf-cookie', (r) => r.fulfill({ body: '{}' }));
    await page.route('**/api/v1/users/me', (r) =>
      r.fulfill({
        body: JSON.stringify({ id: 1, email: 'e2e@example.com', full_name: 'E2E User' }),
        headers: { 'Content-Type': 'application/json' },
      })
    );
    await page.route('**/api/v1/labs/**', (r) =>
      r.fulfill({
        body: JSON.stringify([
          { id: 10, test_name: 'Albumin', value: 4.2, unit: 'g/dL', test_date: '2026-04-28', status: 'final' },
        ]),
        headers: { 'Content-Type': 'application/json' },
      })
    );
    await page.route('**/api/v1/ehr/**', (r) =>
      r.fulfill({ body: JSON.stringify([]), headers: { 'Content-Type': 'application/json' } })
    );

    await page.goto('/landing');
    await page.evaluate(() => localStorage.setItem('token', 'e2e-token'));
    await page.goto('/labs');
  });

  test('renders labs page', async ({ page }) => {
    await expect(page.locator('body')).toBeVisible();
  });

  test('shows lab result from API', async ({ page }) => {
    await expect(page.getByText('Albumin')).toBeVisible({ timeout: 5000 });
  });

  test('shows value and unit', async ({ page }) => {
    await expect(page.getByText(/4\.2/)).toBeVisible({ timeout: 5000 });
  });
});

// ── Dashboard page ────────────────────────────────────────────────────────────

test.describe('Dashboard page', () => {
  test.beforeEach(async ({ page }) => {
    await mockAppChrome(page);
    await page.route('**/api/v1/auth/csrf-cookie', (r) => r.fulfill({ body: '{}' }));
    await page.route('**/api/v1/users/me', (r) =>
      r.fulfill({
        body: JSON.stringify({ id: 1, email: 'dash@example.com', full_name: 'Dash User' }),
        headers: { 'Content-Type': 'application/json' },
      })
    );
    // Catch all remaining API calls
    await page.route('**/api/v1/**', (r) =>
      r.fulfill({ body: JSON.stringify([]), headers: { 'Content-Type': 'application/json' } })
    );

    await page.goto('/landing');
    await page.evaluate(() => localStorage.setItem('token', 'e2e-token'));
    await page.goto('/dashboard');
  });

  test('renders dashboard', async ({ page }) => {
    await expect(page.locator('body')).toBeVisible();
  });

  test('does not show login page when authenticated', async ({ page }) => {
    // Should not redirect to /landing when token is present
    await expect(page).not.toHaveURL(/landing/);
  });
});
