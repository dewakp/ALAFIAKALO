import { describe, it, expect, vi } from 'vitest';
import axios from 'axios';

// Mock axios to test how the API client configures it.
vi.mock('axios', () => {
  const instance = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    defaults: { headers: { common: {} } },
    get: vi.fn(),
    post: vi.fn(),
  };
  return { default: { create: vi.fn(() => instance) } };
});

// Importing the module IS the behaviour under test: it creates the instance and
// registers the interceptors at import time. This used to be done with
// `require('axios')` inside each test, which resolved the real axios rather than
// the mock above — so the assertions ran against a function that was never a
// spy, and both tests failed. There is also no vi.resetModules() here on
// purpose: resetting the registry re-runs the mock factory and hands the module
// a *different* instance than the one this file's `axios` binding refers to.
import '../services/api';

describe('API Client', () => {
  it('creates the axios instance with the app defaults', () => {
    expect(axios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        baseURL: '/api/v1',
        timeout: 30000,
        withCredentials: true,
      })
    );
  });

  it('registers request and response interceptors', () => {
    const instance = axios.create.mock.results[0].value;
    expect(instance.interceptors.request.use).toHaveBeenCalled();
    expect(instance.interceptors.response.use).toHaveBeenCalled();
  });
});
