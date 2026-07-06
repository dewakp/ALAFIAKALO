import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn((url) => {
      if (url === '/wellness/score') {
        return Promise.resolve({ data: { score_date: '2026-07-02', overall_score: 74, explanation: 'Based on your recent data.' } });
      }
      if (url === '/labs/') {
        return Promise.resolve({ data: [
          { id: 1, test_date: '2025-08-18', test_name: 'A/G Ratio', value: 1.6, unit: 'Calc', status: 'final', created_at: '2025-08-18T00:00:00' },
          { id: 2, test_date: '2025-08-18', test_name: 'Albumin', value: 4.2, unit: 'g/dL', status: 'final', created_at: '2025-08-18T00:00:00' },
          { id: 3, test_date: '2025-08-18', test_name: 'Alk Phos', value: 618, unit: 'U/L', status: 'final', created_at: '2025-08-18T00:00:00' },
          { id: 4, test_date: '2025-08-18', test_name: 'ALT', value: 30, unit: 'U/L', status: 'final', created_at: '2025-08-18T00:00:00' },
        ] });
      }
      if (url === '/vitals/') {
        return Promise.resolve({ data: [
          { id: 1, log_date: '2026-06-10', blood_pressure_systolic: 120, blood_pressure_diastolic: 80, heart_rate_bpm: 72, created_at: '2026-06-10T00:00:00' },
          { id: 2, log_date: '2026-06-11', blood_pressure_systolic: 118, blood_pressure_diastolic: 78, heart_rate_bpm: 70, created_at: '2026-06-11T00:00:00' },
        ] });
      }
      return Promise.resolve({ data: [] });
    }),
    post: vi.fn(() => Promise.resolve({ data: { suggestions: [{ name: 'Grilled salmon bowl', meal_type: 'lunch', description: 'Salmon with greens.', ingredients: [], pantry_used: [], missing_items: [], calories: 520, rationale: '' }] } })),
  },
}));

import Dashboard from '../pages/Dashboard';

describe('Dashboard (health overview)', () => {
  beforeEach(() => sessionStorage.clear());

  it('renders overview sections, resources, and daily review without crashing', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    expect(screen.getByText('Health Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Current Wellness Score')).toBeInTheDocument();
    expect(screen.getByText('Latest Lab Results')).toBeInTheDocument();
    expect(screen.getByText('Historical Vitals Trend')).toBeInTheDocument();
    expect(screen.getByText('Alafia Personalized Recommendations')).toBeInTheDocument();
    expect(screen.getByText('Alafia Health Insights (Experimental)')).toBeInTheDocument();
    expect(screen.getByText('Daily Food Ideas')).toBeInTheDocument();
    expect(screen.getByText('Resources')).toBeInTheDocument();
    expect(screen.getByText('Daily Review')).toBeInTheDocument();
    expect(screen.getByText('Alafia is a 6igma Health App.')).toBeInTheDocument();

    // Async data resolves into the cards
    expect(await screen.findByText('74')).toBeInTheDocument();
    expect(await screen.findByText('Lab Draw Report')).toBeInTheDocument();
    expect(await screen.findByText('…and 1 more.')).toBeInTheDocument();
    expect(await screen.findByText(/Grilled salmon bowl/)).toBeInTheDocument();

    // Resource quick links present
    expect(screen.getByText('Chat with Alafia')).toBeInTheDocument();
    expect(screen.getByText('Connect Records')).toBeInTheDocument();
  });
});
