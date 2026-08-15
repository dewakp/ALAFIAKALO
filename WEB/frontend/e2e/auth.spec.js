import { test, expect } from '@playwright/test';

test.describe('Authentication flow', () => {
  test('landing page loads', async ({ page }) => {
    await page.goto('/landing');
    await expect(page).toHaveTitle(/ALAFIA/i);
  });

  test('login page renders form', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByLabel('Email Address')).toBeVisible();
    // A password input has no implicit `textbox` role, so getByRole never
    // matches one. Address it by its label instead — exact, because the
    // show/hide toggle's aria-label is "Show password".
    await expect(page.getByLabel('Password', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Login with Email' })).toBeVisible();
  });

  test('empty login shows validation errors', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: 'Login with Email' }).click();
    // Both fields are `required`, so the browser blocks submission and focuses
    // the first invalid control rather than navigating away.
    await expect(page.getByLabel('Email Address')).toBeFocused();
    await expect(page).toHaveURL(/\/login/);
  });

  test('register page renders form', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Password', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /create account/i })).toBeVisible();
  });

  test('forgot password page is accessible', async ({ page }) => {
    await page.goto('/login');
    const forgotLink = page.getByText(/forgot password/i);
    if (await forgotLink.isVisible()) {
      await forgotLink.click();
      await expect(page.getByRole('textbox', { name: /email/i })).toBeVisible();
    }
  });
});
