import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { useAuth } from './AuthContext';
import {
  METRIC,
  IMPERIAL,
  unitLabel,
  convertForDisplay,
  convertToMetric,
  formatQuantity,
} from '../utils/units';

const UnitsContext = createContext(null);

const STORAGE_KEY = 'alafia_units';

/**
 * Holds the active measurement system (metric | imperial) as a single source of
 * truth and persists changes to the backend (`PATCH /users/me`) + localStorage.
 *
 * Seed order: localStorage → user.preferred_units → metric (the global default).
 * Must be mounted inside <AuthProvider> so it can read the logged-in user.
 */
export function UnitsProvider({ children }) {
  const { user } = useAuth();
  const [system, setSystemState] = useState(() => localStorage.getItem(STORAGE_KEY) || METRIC);

  // Once the user loads, adopt their stored preference (unless the user has
  // already made a local choice this session).
  useEffect(() => {
    if (user?.preferred_units && !localStorage.getItem(STORAGE_KEY)) {
      setSystemState(user.preferred_units === IMPERIAL ? IMPERIAL : METRIC);
    }
  }, [user]);

  const setSystem = useCallback((next) => {
    const value = next === IMPERIAL ? IMPERIAL : METRIC;
    setSystemState(value);
    localStorage.setItem(STORAGE_KEY, value);
    // Best-effort persistence; UI already reflects the change optimistically.
    api.patch('/users/me', { preferred_units: value }).catch(() => {});
  }, []);

  const toggleSystem = useCallback(() => {
    setSystem(system === IMPERIAL ? METRIC : IMPERIAL);
  }, [system, setSystem]);

  const value = {
    system,
    isImperial: system === IMPERIAL,
    setSystem,
    toggleSystem,
    // Helpers bound to the active system so callers don't pass it every time.
    unitLabel: (measurement) => unitLabel(measurement, system),
    toDisplay: (v, measurement) => convertForDisplay(v, measurement, system),
    toMetric: (v, measurement) => convertToMetric(v, measurement, system),
    format: (v, measurement, precision) => formatQuantity(v, measurement, system, precision),
  };

  return <UnitsContext.Provider value={value}>{children}</UnitsContext.Provider>;
}

export function useUnits() {
  const ctx = useContext(UnitsContext);
  if (!ctx) throw new Error('useUnits must be used within UnitsProvider');
  return ctx;
}
