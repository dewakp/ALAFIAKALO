import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/api', () => ({
  default: { get: vi.fn(() => Promise.resolve({ data: { count: 0 } })) },
}));

// Swapped per test to stand in for a patient or a clinician account.
let mockUser = null;
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: mockUser, logout: vi.fn() }),
  AuthProvider: ({ children }) => children,
}));

import Layout from '../components/Layout';
import { ClinicianModeProvider } from '../context/ClinicianModeContext';

const renderLayout = () =>
  render(
    <MemoryRouter>
      <ClinicianModeProvider><Layout /></ClinicianModeProvider>
    </MemoryRouter>
  );

const PATIENT = { full_name: 'Pat Patient', primary_role: 'patient', active_roles: ['patient'] };
const CLINICIAN = {
  full_name: 'Dr Clinician',
  primary_role: 'physician',
  active_roles: ['patient', 'physician'],
};

beforeEach(() => { mockUser = null; });

describe('sharing in the main nav', () => {
  it('is a top-level link, not buried in a collapsed group', () => {
    mockUser = PATIENT;
    renderLayout();

    // Collapsed groups render no children until opened, so finding the link
    // without clicking anything is the assertion: it is top level.
    const link = screen.getByRole('link', { name: /Share Records/i });
    expect(link).toHaveAttribute('href', '/data-sharing');
  });
});

describe('persona switcher', () => {
  it('is hidden for an account with no clinical role', () => {
    mockUser = PATIENT;
    renderLayout();
    expect(screen.queryByRole('button', { name: /Clinician/i })).toBeNull();
  });

  it('is shown for a physician', () => {
    mockUser = CLINICIAN;
    renderLayout();
    expect(screen.getByRole('button', { name: /Clinician/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Patient/i })).toBeTruthy();
  });

  it('swaps the navigation when switched to clinician', () => {
    mockUser = CLINICIAN;
    renderLayout();

    // Patient nav before the switch.
    expect(screen.getByRole('link', { name: /Medications/i })).toBeTruthy();
    expect(screen.queryByRole('link', { name: /My Patients/i })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Clinician/i }));

    // Clinical nav after it — and the patient-only entries are gone, rather
    // than the clinical ones being appended to them.
    expect(screen.getByRole('link', { name: /My Patients/i })).toHaveAttribute(
      'href', '/clinician-dashboard',
    );
    expect(screen.queryByRole('link', { name: /Medications/i })).toBeNull();
    // Sharing survives the swap: a clinician shares records too.
    expect(screen.getByRole('link', { name: /Share Records/i })).toBeTruthy();
  });

  it('switches back to the patient navigation', () => {
    mockUser = CLINICIAN;
    renderLayout();

    fireEvent.click(screen.getByRole('button', { name: /Clinician/i }));
    expect(screen.getByRole('link', { name: /My Patients/i })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Patient/i }));
    expect(screen.queryByRole('link', { name: /My Patients/i })).toBeNull();
    expect(screen.getByRole('link', { name: /Medications/i })).toBeTruthy();
  });

  it('drops a patient account out of clinician mode', () => {
    // A clinician signs in, switches mode, signs out; a patient signs in on the
    // same session. The mode must not carry over — it is derived from the
    // current user's roles, not remembered.
    mockUser = CLINICIAN;
    const { rerender } = renderLayout();
    fireEvent.click(screen.getByRole('button', { name: /Clinician/i }));
    expect(screen.getByRole('link', { name: /My Patients/i })).toBeTruthy();

    mockUser = PATIENT;
    rerender(
      <MemoryRouter>
        <ClinicianModeProvider><Layout /></ClinicianModeProvider>
      </MemoryRouter>
    );
    expect(screen.queryByRole('link', { name: /My Patients/i })).toBeNull();
  });
});
