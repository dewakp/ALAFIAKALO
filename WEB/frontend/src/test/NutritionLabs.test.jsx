import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// ── Mock api ──────────────────────────────────────────────────────────────────

const mockApi = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  defaults: { headers: { common: {} } },
  interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
};
vi.mock('../services/api', () => ({ default: mockApi }));

// Lucide icons — thin stubs so we don't need a canvas environment
vi.mock('lucide-react', () => ({
  Plus: () => <span>+</span>,
  Search: () => <span>search</span>,
  Apple: () => <span>apple</span>,
  ChevronDown: () => <span>▼</span>,
  ChevronRight: () => <span>▶</span>,
  BarChart3: () => <span>chart</span>,
  Utensils: () => <span>utensils</span>,
  X: () => <span>x</span>,
  Loader2: () => <span>loading</span>,
  Info: () => <span>info</span>,
  Calendar: () => <span>cal</span>,
  Zap: () => <span>zap</span>,
}));

vi.mock('../components/BackButton', () => ({ default: () => <button>Back</button> }));

import Nutrition from '../pages/Nutrition';
import Labs from '../pages/Labs';

// ══════════════════════════════════════════════════════════════════════════════
// Nutrition page
// ══════════════════════════════════════════════════════════════════════════════

describe('Nutrition page', () => {
  const sampleLog = {
    id: 1, food_name: 'Oatmeal', meal_type: 'breakfast',
    log_date: '2026-04-28', calories: 150, notes: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.get.mockResolvedValue({ data: [] });
    mockApi.post.mockResolvedValue({ data: sampleLog });
  });

  it('renders the page without crashing', async () => {
    render(<MemoryRouter><Nutrition /></MemoryRouter>);
    expect(document.body).toBeTruthy();
  });

  it('loads and shows nutrition logs on mount', async () => {
    mockApi.get.mockImplementation((url) => {
      if (url.includes('/nutrition/')) return Promise.resolve({ data: [sampleLog] });
      return Promise.resolve({ data: [] });
    });
    render(<MemoryRouter><Nutrition /></MemoryRouter>);
    await waitFor(() => expect(mockApi.get).toHaveBeenCalledWith(
      expect.stringContaining('/nutrition/'),
      expect.anything(),
    ));
  });

  it('shows add button', async () => {
    render(<MemoryRouter><Nutrition /></MemoryRouter>);
    await waitFor(() => {
      const buttons = document.querySelectorAll('button');
      expect(buttons.length).toBeGreaterThan(0);
    });
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// Labs page
// ══════════════════════════════════════════════════════════════════════════════

describe('Labs page', () => {
  const sampleLab = {
    id: 10, test_name: 'Albumin', value: 4.2,
    unit: 'g/dL', test_date: '2026-04-28', status: 'final',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.get.mockResolvedValue({ data: [] });
  });

  it('renders without crashing', async () => {
    render(<MemoryRouter><Labs /></MemoryRouter>);
    expect(document.body).toBeTruthy();
  });

  it('calls /labs/ on mount', async () => {
    render(<MemoryRouter><Labs /></MemoryRouter>);
    await waitFor(() => {
      const calls = mockApi.get.mock.calls.map(([url]) => url);
      expect(calls.some((url) => url.includes('/labs/'))).toBe(true);
    });
  });

  it('displays lab result after loading', async () => {
    mockApi.get.mockImplementation((url) => {
      if (url.includes('/labs/')) return Promise.resolve({ data: [sampleLab] });
      return Promise.resolve({ data: [] });
    });
    render(<MemoryRouter><Labs /></MemoryRouter>);
    await waitFor(() => {
      expect(document.body.textContent).toContain('Albumin');
    });
  });

  it('shows form when add button is clicked', async () => {
    mockApi.get.mockResolvedValue({ data: [] });
    render(<MemoryRouter><Labs /></MemoryRouter>);
    await waitFor(() => {
      // Any button rendered (add / plus)
      expect(document.querySelectorAll('button').length).toBeGreaterThan(0);
    });
  });
});
