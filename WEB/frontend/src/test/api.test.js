import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';

// Mock axios to test API client configuration
vi.mock('axios', () => {
  const interceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  };
  const instance = {
    interceptors,
    defaults: { headers: { common: {} } },
    get: vi.fn(),
    post: vi.fn(),
  };
  return {
    default: {
      create: vi.fn(() => instance),
    },
  };
});

describe('API Client', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('creates axios instance with correct baseURL', () => {
    // Re-import to trigger axios.create
    const axiosImport = require('axios').default;
    require('../services/api');
    expect(axiosImport.create).toHaveBeenCalledWith(
      expect.objectContaining({
        baseURL: '/api/v1',
        timeout: 30000,
        withCredentials: true,
      })
    );
  });

  it('registers request and response interceptors', () => {
    const axiosImport = require('axios').default;
    const api = axiosImport.create();
    require('../services/api');
    expect(api.interceptors.request.use).toHaveBeenCalled();
    expect(api.interceptors.response.use).toHaveBeenCalled();
  });
});
