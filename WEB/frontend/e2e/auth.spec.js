import { test, expect } from '@playwright/test';

test.describe('Authentication flow', () => {
  test('landing page loads', async ({ page }) => {
    await page.goto('/landing');
    await expect(page).toHaveTitle(/ALAFIA/i);
  });

  test('login page renders form', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByRole('textbox', { name: /email/i })).toBeVisible();
    await expect(page.getByRole('textbox', { name: /password/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /login|sign in/i })).toBeVisible();
  });

  test('empty login shows validation errors', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: /login|sign in/i }).click();
    // Browser native validation or inline error
    const emailField = page.getByRole('textbox', { name: /email/i });
    await expect(emailField).toBeFocused();
  });

  test('register page renders form', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByRole('textbox', { name: /email/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /register|sign up/i })).toBeVisible();
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
