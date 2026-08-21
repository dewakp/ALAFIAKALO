import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  withCredentials: true,
});

/**
 * Timeout for endpoints that wait on an LLM. Pass explicitly:
 *   api.post('/planners/meal-suggestions', body, { timeout: AI_TIMEOUT_MS })
 *
 * The 30s default above is right for ordinary CRUD and wrong for generation.
 * A production meal-suggestion request measured 99s and 121s end to end — the
 * model was up and answering at ~51 tokens/s, it simply takes that long to
 * produce ~2,600 tokens. The browser aborted at 30s and the user was told the
 * AI was "unavailable", which sent us looking for a service that was never down.
 *
 * The ladder has to stay ordered, longest last, or the client hides the
 * server's real error behind a generic abort:
 *
 *   client 240s  <  backend OLLAMA_TIMEOUT 300s  =  Cloud Run 300s  <  Ollama 600s
 *
 * This is a ceiling, not a target. The durable fix for slow generation is the
 * async pattern nutrition already uses (CLAUDE.md §3c): persist immediately,
 * fill in from a background task, and let the client poll.
 */
export const AI_TIMEOUT_MS = 240000;

export function getCookieValue(name) {
  return document.cookie
    .split('; ')
    .find((cookie) => cookie.startsWith(`${name}=`))
    ?.split('=')[1];
}

export async function ensureCsrfToken() {
  let csrfToken = getCookieValue('csrf_token');
  if (csrfToken) return csrfToken;

  await fetch('/api/v1/auth/csrf-cookie', { credentials: 'same-origin' });
  csrfToken = getCookieValue('csrf_token');
  return csrfToken || '';
}

export async function refreshAccessToken() {
  const { data } = await api.post('/auth/refresh');
  localStorage.setItem('token', data.access_token);
  api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
  return data.access_token;
}

// Attach JWT token + CSRF token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Double-submit CSRF: read cookie and send as header on mutating requests
  const method = (config.method || '').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = getCookieValue('csrf_token');
    if (csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken;
    }
  }
  return config;
});

// Handle 401 — attempt token refresh, then retry original request
let isRefreshing = false;
let failedQueue = [];

function processQueue(error, token = null) {
  failedQueue.forEach((prom) => {
    if (error) prom.reject(error);
    else prom.resolve(token);
  });
  failedQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      // Already a refresh request — give up
      if (originalRequest.url?.includes('/auth/refresh')) {
        localStorage.removeItem('token');
        window.location.href = '/login';
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // Cookie is sent automatically via withCredentials
        const accessToken = await refreshAccessToken();
        processQueue(null, accessToken);
        originalRequest.headers.Authorization = `Bearer ${accessToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        localStorage.removeItem('token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    // 402 — an active subscription is required: send the user to the paywall page.
    if (error.response?.status === 402
        && !window.location.pathname.startsWith('/subscription')) {
      window.location.href = '/subscription';
    }

    return Promise.reject(error);
  }
);

export default api;
