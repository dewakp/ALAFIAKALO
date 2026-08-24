import { defineConfig, configDefaults } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    // vitest's default include matches every *.spec.js, which swept up the
    // Playwright suite in e2e/ and failed it with "Playwright Test did not
    // expect test.describe() to be called here". Those specs run under
    // `npx playwright test`, not vitest.
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    // Vite rejects requests whose Host header it does not recognise (403
    // "Blocked request"), which is a DNS-rebinding guard. Inside compose the
    // e2e container reaches this server by its SERVICE NAME, so that name has
    // to be allowed or every page loads empty and every spec fails on a blank
    // title. Dev server only — this never ships.
    allowedHosts: ['localhost', 'frontend-dev'],
    // Inside the frontend-dev container `localhost` is that container, not the
    // host, so the proxy target has to be the backend SERVICE (backend:8000).
    // Compose sets VITE_API_PROXY_TARGET; the default keeps a host-run
    // `npm run dev` working against the published port.
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8005',
        changeOrigin: true,
      },
    },
    // Bind mounts on macOS do not deliver inotify events into the container, so
    // HMR sees no file changes without polling.
    watch: process.env.VITE_POLL ? { usePolling: true, interval: 300 } : undefined,
  },

  // `vite preview` serves the built bundle and applies the same host check as
  // the dev server. The e2e container reaches it by service name.
  preview: {
    port: 5173,
    host: '0.0.0.0',
    allowedHosts: ['localhost', 'frontend-preview'],
    // The SAME proxy as the dev server. Without it `/api` in preview mode has
    // nowhere to go and vite answers 500 text/plain — so no e2e spec could ever
    // reach the real backend, and every spec had to mock the API. That is how a
    // suite stays green while the actual client/server contract drifts: the
    // trailing-slash redirect that broke Notifications was invisible to 27
    // passing specs for exactly this reason.
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8005',
        changeOrigin: true,
      },
    },
  },
});
