import { expect, test } from '@playwright/test';
import { mockAppChrome } from './helpers.js';

/**
 * The two-step signup, driven end to end in a real browser.
 *
 * This flow shipped as four backend endpoints with NO client, which is why
 * `TWO_STEP_SIGNUP_REQUIRED` could never be turned on and why an account
 * reached production having "gone through" with neither an email nor a
 * payment. The parts a unit test cannot reach are exactly the ones that broke:
 * the API paths (the router mounts at /auth/signup, not /signup), the redirect
 * out to Stripe, and the return leg — whose success URL carries a session id
 * and no email at all.
 */

const json = (body, status = 200) => ({
  status,
  body: JSON.stringify(body),
  headers: { 'Content-Type': 'application/json' },
});

async function stubSignup(page, { onStart, onCheckout, onComplete } = {}) {
  await mockAppChrome(page);
  await page.route('**/api/v1/auth/signup/start', (r) => {
    onStart?.(JSON.parse(r.request().postData() || '{}'));
    return r.fulfill(json({ message: 'sent', pending_id: 1 }, 202));
  });
  await page.route('**/api/v1/auth/signup/checkout', (r) => {
    onCheckout?.(JSON.parse(r.request().postData() || '{}'));
    return r.fulfill(json({
      provider: 'stripe',
      // Where Stripe actually returns to, verbatim from subscription_service.
      checkout_url: '/signup/complete?provider=stripe&session_id=cs_test_e2e',
      reference_id: 'cs_test_e2e',
      test_mode: true,
    }));
  });
  await page.route('**/api/v1/auth/signup/complete', (r) => {
    const body = JSON.parse(r.request().postData() || '{}');
    onComplete?.(body);
    return r.fulfill(json({
      message: 'Payment received.',
      paid: true, email_verified: false, email: body.email,
    }));
  });
}

async function fillDetails(page, { first = 'Adaeze', last = 'Okafor' } = {}) {
  await page.getByLabel('First Name').fill(first);
  await page.getByLabel('Last Name').fill(last);
  await page.getByLabel('Email').fill('ada@example.com');
  await page.getByLabel('Date of Birth').fill('1990-01-01');
  await page.locator('#su-password').fill('SecureP@ss123');
}

test('details are sent as two name fields, then the page moves to payment', async ({ page }) => {
  let sent = null;
  await stubSignup(page, { onStart: (b) => { sent = b; } });

  await page.goto('/signup');
  await fillDetails(page);
  await page.getByRole('button', { name: 'Continue' }).click();

  // The whole point of the split: nothing downstream has to guess a surname.
  await expect.poll(() => sent?.first_name).toBe('Adaeze');
  expect(sent.last_name).toBe('Okafor');

  // "the app page should transition into payment page" — without waiting for
  // the email to be clicked.
  await expect(page.getByRole('button', { name: /Continue to payment/ })).toBeVisible();
  await expect(page.getByText(/verification link/i)).toBeVisible();
});

test('a two-letter name is refused before any request is made', async ({ page }) => {
  let called = false;
  await stubSignup(page, { onStart: () => { called = true; } });

  await page.goto('/signup');
  await fillDetails(page, { first: 'Li' });
  await page.getByRole('button', { name: 'Continue' }).click();

  // Two mechanisms refuse this and either is fine: the browser's own
  // `minLength` (field-anchored, and it fires first) or the JS check behind
  // it. What must be true is that NOTHING was sent — asserting the specific
  // message would pin the mechanism instead of the behaviour, and the message
  // only appears on the browsers that skip native validation.
  const first = page.getByLabel('First Name');
  await expect(first).toHaveJSProperty('validity.valid', false);
  expect(called).toBe(false);

  // And it clears the moment the name is long enough — a rule that cannot be
  // satisfied is worse than no rule.
  await first.fill('Adaeze');
  await expect(first).toHaveJSProperty('validity.valid', true);
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect.poll(() => called).toBe(true);
});

test('the return from Stripe completes the signup it started', async ({ page }) => {
  let completed = null;
  await stubSignup(page, { onComplete: (b) => { completed = b; } });

  await page.goto('/signup');
  await fillDetails(page);
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: /Continue to payment/ }).click();

  // Stripe's success_url carries a session id and NO email. The address has to
  // survive the hop or the payment cannot be attached to any account.
  await expect.poll(() => completed?.email).toBe('ada@example.com');
  expect(completed.reference_id).toBe('cs_test_e2e');

  // Paid-but-unverified is a real state, not an error: the money is taken and
  // the link is unread. Reporting a failure here would be false.
  await expect(page.getByText(/Payment received/i)).toBeVisible();
  await expect(page.getByText(/verification link/i)).toBeVisible();
});

test('returning without the parked address asks for it instead of dead-ending', async ({ page }) => {
  await stubSignup(page);
  // A fresh tab: the payment completed, sessionStorage is empty.
  await page.goto('/signup/complete?provider=stripe&session_id=cs_test_e2e');
  await expect(page.getByText(/payment went through/i)).toBeVisible();
  await expect(page.getByLabel('Email')).toBeVisible();
});

test('backing out of Stripe is not reported as a failure', async ({ page }) => {
  await stubSignup(page);
  await page.goto('/signup?status=cancel');
  await expect(page.getByText(/No payment was taken/i)).toBeVisible();
  // and the way forward is still there
  await expect(page.getByRole('button', { name: /Continue to payment/ })).toBeVisible();
});

test('the verification link has a page to land on', async ({ page }) => {
  await mockAppChrome(page);
  await page.route('**/api/v1/auth/signup/verify-email', (r) =>
    r.fulfill(json({ email: 'ada@example.com', email_verified: true, paid: true, next: 'complete' })));
  await page.route('**/api/v1/auth/signup/status**', (r) =>
    r.fulfill(json({ email: 'ada@example.com', email_verified: true, paid: true, next: 'complete' })));

  // The email has always pointed here and no route existed.
  await page.goto('/verify-email?token=abc123');
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
});

test('an expired link says so and offers a way forward', async ({ page }) => {
  await mockAppChrome(page);
  await page.route('**/api/v1/auth/signup/verify-email', (r) =>
    r.fulfill(json({ detail: 'That link has expired.' }, 400)));

  await page.goto('/verify-email?token=stale');
  await expect(page.getByRole('alert')).toContainText(/expired/i);
  await expect(page.getByRole('link', { name: /Start again/i })).toBeVisible();
});
