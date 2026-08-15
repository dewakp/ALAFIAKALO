import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['html', { open: 'never' }], ['list']],

  // Every route in App.jsx is React.lazy, and the dev server compiles each chunk
  // on its first request. With parallel workers that first hit lands inside a
  // test, so a cold chunk ate most of the default 5s budget and a different
  // spec failed on each run. The work is real, so wait for it rather than
  // pretending the app is slow.
  expect: { timeout: 15_000 },

  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    navigationTimeout: 30_000,
    actionTimeout: 15_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Serve a real build rather than the dev server (local only).
  //
  // Skipped entirely when PLAYWRIGHT_BASE_URL is set: that means the suite is
  // pointed at a server someone else is running — the `frontend-dev` container,
  // or a deployed URL — and starting a second one here would test the wrong
  // thing while fighting for the port.
  //
  // `npm run dev` compiles each lazy route chunk on its first request, and with
  // parallel workers that compile happens *inside* whichever test got there
  // first — so a different spec failed on every cold run. Previewing a built
  // bundle removes the race entirely, and tests the assets that actually ship.
  webServer: (process.env.CI || process.env.PLAYWRIGHT_BASE_URL) ? undefined : {
    command: 'npm run build && npm run preview -- --port 5173 --strictPort',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
