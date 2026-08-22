import { test, expect, devices } from '@playwright/test';
import { mockAppChrome, signIn } from './helpers.js';

/**
 * The sidebar was `display: none` below 768px with nothing in its place, so an
 * authenticated phone user had NO navigation at all: Conditions, Medications,
 * Labs and Therapies were unreachable except by typing a URL.
 *
 * Unit tests cannot catch this — jsdom has no viewport and does not apply media
 * queries. It needs a real browser at a real phone width.
 */

test.use({ ...devices['Pixel 7'] });

test.describe('Mobile navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockAppChrome(page);
    await page.route('**/api/v1/chronic/conditions**', (r) =>
      r.fulfill({ body: '[]', headers: { 'Content-Type': 'application/json' } }));
    await signIn(page);
  });

  test('an authenticated phone user has a way to open navigation', async ({ page }) => {
    await page.goto('/');
    // The regression in one assertion: on a phone there must be a control that
    // opens the menu.
    await expect(page.getByRole('button', { name: 'Open menu' })).toBeVisible();
  });

  test('the drawer reveals the nav links and they work', async ({ page }) => {
    await page.goto('/');

    // Closed: the sidebar is translated off-canvas, so its links are present
    // but not in view.
    const conditions = page.getByRole('link', { name: 'Conditions' });
    await expect(conditions).not.toBeInViewport();

    await page.getByRole('button', { name: 'Open menu' }).click();
    await expect(conditions).toBeInViewport();

    await conditions.click();
    await expect(page).toHaveURL(/chronic-conditions/);
  });

  test('navigating closes the drawer instead of covering the page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Open menu' }).click();
    await page.getByRole('link', { name: 'Conditions' }).click();
    await expect(page.getByRole('link', { name: 'Conditions' })).not.toBeInViewport();
  });

  test('the backdrop dismisses it', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Open menu' }).click();
    await expect(page.getByRole('link', { name: 'Conditions' })).toBeInViewport();

    // Tap well clear of the 320px-max drawer.
    await page.mouse.click(370, 400);
    await expect(page.getByRole('link', { name: 'Conditions' })).not.toBeInViewport();
  });
});

test.describe('Desktop is unchanged', () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test('no mobile chrome, and the sidebar is simply there', async ({ page }) => {
    await mockAppChrome(page);
    await signIn(page);
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Open menu' })).toBeHidden();
    await expect(page.getByRole('link', { name: 'Conditions' })).toBeInViewport();
  });
});
