/**
 * Mock the endpoints the app chrome calls on every authenticated page.
 *
 * Left unmocked these return 401, the axios interceptor treats that as a dead
 * session, and the app redirects to /login mid-test. Specs then pass only by
 * asserting before the redirect lands — a race. Adding one lazy route chunk
 * elsewhere in the app was enough to lose that race on the dev server, which
 * looked exactly like an unrelated regression in Nutrition and Labs.
 *
 * Register this BEFORE the spec's own routes: Playwright gives precedence to
 * the most recently registered matching handler, so a spec can still override
 * any of these.
 */
export async function mockAppChrome(page) {
  const json = (body) => ({
    body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json' },
  });
  await page.route('**/api/v1/auth/csrf-cookie', (r) => r.fulfill({ body: '{}' }));
  await page.route('**/api/v1/auth/refresh', (r) =>
    r.fulfill(json({ access_token: 'e2e-token' })));
  await page.route('**/api/v1/users/me', (r) =>
    r.fulfill(json({ id: 1, email: 'e2e@example.com', full_name: 'E2E User' })));
  await page.route('**/api/v1/notifications/unread-count**', (r) => r.fulfill(json({ count: 0 })));
  await page.route('**/api/v1/subscription/status**', (r) =>
    r.fulfill(json({ tier: 'free', active: true })));
  await page.route('**/api/v1/ehr/connections**', (r) => r.fulfill(json([])));
}

/** Put the app in a signed-in state without touching a real backend. */
export async function signIn(page) {
  await page.goto('/landing');
  await page.evaluate(() => localStorage.setItem('token', 'e2e-token'));
}
