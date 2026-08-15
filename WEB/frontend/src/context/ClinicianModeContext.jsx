import { createContext, useContext, useMemo, useState } from 'react';
import { useAuth } from './AuthContext';

// Roles that can enter clinician mode. This list lives here rather than in
// Layout because three separate places used to need it — the nav, the Role page
// and the dashboard — and a copy in each is how they drift apart.
export const CLINICIAN_ROLES = [
  'physician', 'surgeon', 'nurse_practitioner',
  'physician_assistant', 'resident', 'fellow', 'attending_physician',
  'cardiologist', 'dermatologist', 'endocrinologist', 'gastroenterologist',
  'neurologist', 'oncologist', 'pediatrician', 'radiologist',
  'general_surgeon', 'orthopedic_surgeon', 'neurosurgeon',
  'cardiothoracic_surgeon', 'plastic_surgeon', 'vascular_surgeon',
  'oral_surgeon', 'clinical_nurse_specialist', 'nurse_anesthetist',
  'nurse_midwife', 'charge_nurse', 'nurse_administrator',
  'medical_director', 'chief_medical_officer',
];

/** True when the user holds any role that can practise in clinician mode. */
export function isClinician(user) {
  if (!user) return false;
  const roles = [...(user.active_roles || [])];
  if (user.primary_role) roles.push(user.primary_role);
  return roles.some(r => CLINICIAN_ROLES.includes(r));
}

/** The clinician role the user actually holds, for labelling the switcher. */
export function clinicianRoleOf(user) {
  if (!user) return null;
  const roles = [...(user.active_roles || [])];
  if (user.primary_role) roles.push(user.primary_role);
  return roles.find(r => CLINICIAN_ROLES.includes(r)) || null;
}

const ClinicianModeContext = createContext(null);

export function ClinicianModeProvider({ children }) {
  const { user } = useAuth();
  const [requested, setRequested] = useState(false);

  const value = useMemo(() => {
    const canBeClinician = isClinician(user);
    // Derive rather than store. A patient account signing in after a clinician
    // must never inherit the previous session's mode, and a user whose role is
    // revoked mid-session must drop out of it on the next render — neither is
    // true if the flag is trusted on its own.
    const clinicianMode = requested && canBeClinician;
    return {
      clinicianMode,
      canBeClinician,
      clinicianRole: clinicianRoleOf(user),
      enterClinicianMode: () => setRequested(true),
      exitClinicianMode: () => setRequested(false),
      // Where each mode starts. The switcher navigates here so a physician who
      // flips modes from, say, /nutrition does not land on a page their new nav
      // no longer lists.
      homePath: clinicianMode ? '/clinician-dashboard' : '/',
    };
  }, [user, requested]);

  return (
    <ClinicianModeContext.Provider value={value}>
      {children}
    </ClinicianModeContext.Provider>
  );
}

export function useClinicianMode() {
  const ctx = useContext(ClinicianModeContext);
  if (!ctx) throw new Error('useClinicianMode must be used within ClinicianModeProvider');
  return ctx;
}
