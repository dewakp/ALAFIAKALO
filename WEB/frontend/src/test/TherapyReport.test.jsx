import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const get = vi.fn();
const post = vi.fn();
vi.mock('../services/api', () => ({
  default: {
    get: (...a) => get(...a),
    post: (...a) => post(...a),
    defaults: { headers: { common: {} } },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

import TherapyReport from '../pages/clinician/TherapyReport';

// Shaped exactly like the rows the category endpoint returns for `dialysis`.
const rows = [
  {
    session_id: 2740, date: '2026-08-15', therapy: 'Hemodialysis', name: null,
    status: 'completed', pre_weight_kg: 55.1, post_weight_kg: 55.3,
    fluid_removed_ml: -200, duration_minutes: null, pre_bp: '92/64',
    post_bp: '94/55', pre_heart_rate: 96, post_heart_rate: 106, readings: 6,
    flowsheet_status: null, reviewed_at: null,
  },
  {
    session_id: 2739, date: '2026-08-12', therapy: 'Hemodialysis',
    name: 'Home Hemodialysis (HHD)', status: 'completed',
    pre_weight_kg: 53.7, post_weight_kg: 54, fluid_removed_ml: -300,
    duration_minutes: 165, pre_bp: '92/63', post_bp: '70/40', readings: 3,
    flowsheet_status: 'reviewed', reviewed_at: '2026-08-16T07:23:29Z',
  },
  // A peritoneal row: no session_id, so it must not become a clickable session.
  { session_id: null, date: '2026-08-01', therapy: 'Peritoneal Dialysis', readings: 0 },
];

// The list now also asks for server-computed tiles, so every test needs a
// default: an unmocked call returns undefined and blows up on `.then`.
const SUMMARY = {
  period_days: 90, total_sessions: 2, total_sessions_all_time: 2005,
  avg_pre_weight_kg: 54.4, avg_post_weight_kg: 54.65,
  avg_fluid_removed_ml: -250, avg_duration_min: 165,
  earliest_session: '2013-05-21', latest_session: '2026-08-15',
};
const routeGet = (url) => {
  if (url.includes('therapy-summary')) return Promise.resolve({ data: SUMMARY });
  return Promise.resolve({ data: {} });
};

beforeEach(() => {
  get.mockReset(); post.mockReset();
  get.mockImplementation(routeGet);
});

describe('TherapyReport — the list the physician lands on', () => {
  it('summarises the window in stat tiles instead of a bare table', () => {
    render(<TherapyReport patientId={63} rows={rows} days={90} />);
    // Two HD sessions; the PD row is excluded from the session count.
    expect(screen.getByText('Sessions')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('Avg Pre Wt')).toBeInTheDocument();
    expect(screen.getByText('54.4 kg')).toBeInTheDocument();   // from the server, not the page
    // "165 min" also appears on the session card, so assert the TILE's own
    // value rather than any occurrence of the string.
    expect(screen.getByText('Avg Duration').previousSibling).toHaveTextContent('165 min');
  });

  it('does not treat a missing duration as zero', () => {
    get.mockImplementation((url) =>
      url.includes('therapy-summary') ? Promise.reject(new Error('down')) : Promise.resolve({ data: {} }));
    render(<TherapyReport patientId={63} rows={rows} days={90} />);
    // One of the two sessions has duration null. Averaging it as 0 would give
    // 82.5 — a plausible-looking number that is simply wrong.
    expect(screen.queryByText('82 min')).not.toBeInTheDocument();
    expect(screen.queryByText('83 min')).not.toBeInTheDocument();
  });

  it('shows BP and HR on the card, the way the patient view does', () => {
    render(<TherapyReport patientId={63} rows={rows} days={90} />);
    expect(screen.getByText(/92\/64/)).toBeInTheDocument();
    expect(screen.getByText(/106/)).toBeInTheDocument();
  });

  it('marks an already-reviewed session so a physician does not re-sign blind', () => {
    render(<TherapyReport patientId={63} rows={rows} days={90} />);
    expect(screen.getByText('reviewed')).toBeInTheDocument();
  });

  it('reports an empty window as empty, not as an error', () => {
    render(<TherapyReport patientId={63} rows={[]} days={30} />);
    expect(screen.getByText(/No therapy sessions in this period/i)).toBeInTheDocument();
  });
});

describe('TherapyReport — opening one session', () => {
  it('loads the session report and plots the intradialytic readings', async () => {
    const report = {
      patient: { user_id: 63, full_name: 'Test Patient' },
      session: { id: 2740, date: '2026-08-15', therapy: 'hemodialysis',
                 pre_dialysis_weight_kg: 55.1, post_dialysis_weight_kg: 55.3,
                 fluid_removed_ml: -200, duration_minutes: null },
      readings: [
        { id: 1, reading_time: '12:08', systolic_bp: 99, diastolic_bp: 62, pulse: 94 },
        { id: 2, reading_time: '12:12', systolic_bp: 90, diastolic_bp: 75, pulse: 95 },
      ],
      notes: [],
      signoff: { flowsheet_status: null, signed_at: null, reviewed_at: null, payload_hash: null },
    };
    get.mockImplementation((url) =>
      url.includes('therapy-summary') ? Promise.resolve({ data: SUMMARY })
                                      : Promise.resolve({ data: report }));
    render(<TherapyReport patientId={63} rows={rows} days={90} />);
    fireEvent.click(screen.getByText(new Date('2026-08-15T00:00:00').toLocaleDateString()));

    await waitFor(() => expect(get).toHaveBeenCalledWith(
      '/clinician-dashboard/patient/63/therapy-sessions/2740'));
    await waitFor(() => expect(screen.getByText(/Sign-off/i)).toBeInTheDocument());
    // Patient signature state is stated explicitly — attesting on top of an
    // unsigned record is a different act from countersigning a signed one.
    expect(screen.getByText(/not signed/i)).toBeInTheDocument();
  });

  it('surfaces a failed load as an error, never as "no sessions"', async () => {
    get.mockImplementation((url) =>
      url.includes('therapy-summary')
        ? Promise.resolve({ data: SUMMARY })
        : Promise.reject({ response: { data: { detail: 'This patient has not shared therapies' } } }));
    render(<TherapyReport patientId={63} rows={rows} days={90} />);
    fireEvent.click(screen.getByText(new Date('2026-08-15T00:00:00').toLocaleDateString()));
    await waitFor(() =>
      expect(screen.getByText(/has not shared therapies/i)).toBeInTheDocument());
  });

  it('says so when a session has too few readings to draw a curve', async () => {
    get.mockImplementation((url) =>
      url.includes('therapy-summary')
        ? Promise.resolve({ data: SUMMARY })
        : Promise.resolve({ data: {
            patient: { user_id: 63, full_name: 'Test Patient' },
            session: { id: 2740, date: '2026-08-15', therapy: 'hemodialysis' },
            readings: [], notes: [], signoff: {},
          } }));
    render(<TherapyReport patientId={63} rows={rows} days={90} />);
    fireEvent.click(screen.getByText(new Date('2026-08-15T00:00:00').toLocaleDateString()));
    await waitFor(() =>
      expect(screen.getByText(/No intradialytic readings were recorded/i)).toBeInTheDocument());
  });
});

describe('TherapyReport — gaps the physician would otherwise never see', () => {
  it('says how much history sits outside the window', async () => {
    render(<TherapyReport patientId={63} rows={rows} days={90} />);
    // 2 shown, 2005 on record: the window must announce what it is hiding
    // rather than let the physician read it as the whole chart.
    await waitFor(() =>
      expect(screen.getByText(/2005 on record since 2013-05-21/)).toBeInTheDocument());
  });

  it('prefers the server count over the length of the page', async () => {
    get.mockImplementation((url) =>
      url.includes('therapy-summary')
        ? Promise.resolve({ data: { ...SUMMARY, total_sessions: 36 } })
        : Promise.resolve({ data: {} }));
    render(<TherapyReport patientId={63} rows={rows} days={90} />);
    // Two rows on the page, 36 in the window — the tile must not say "2".
    await waitFor(() => expect(screen.getByText('36')).toBeInTheDocument());
  });
});

describe('ReadingsTable', () => {
  it('renders every intradialytic column the patient card shows', async () => {
    const { ReadingsTable } = await import('../pages/clinician/TherapyReport');
    render(<ReadingsTable readings={[{
      id: 1, reading_time: '12:08', systolic_bp: 99, diastolic_bp: 62, pulse: 94,
      mean_arterial_pressure: 74, blood_flow_rate: 300, dialysate_rate: 500,
      uf_rate: 400, uf_volume_removed: 120, arterial_pressure: -120,
      venous_pressure: 140, remarks: 'stable',
    }]} />);
    ['Time', 'BP', 'Pulse', 'MAP', 'BFR', 'DR', 'UFR', 'UF Vol', 'Art P', 'Ven P', 'Remarks']
      .forEach(h => expect(screen.getByText(h)).toBeInTheDocument());
    expect(screen.getByText('99/62')).toBeInTheDocument();
    expect(screen.getByText('stable')).toBeInTheDocument();
  });
});
