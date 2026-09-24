import { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';
import i18n, { normaliseLanguage } from '../i18n';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Always seed the CSRF cookie so it exists before any POST (login, register, etc.)
    api.get('/auth/csrf-cookie').catch(() => {});

    const token = localStorage.getItem('token');
    if (token) {
      api.defaults.headers.common.Authorization = `Bearer ${token}`;
      loadUser();
    } else {
      setLoading(false);
    }
  }, []);

  // The saved profile language becomes the app's language wherever the user is
  // (re)loaded, so the X-Client-Language header — which the backend reads
  // first — never contradicts the patient's own choice.
  useEffect(() => {
    const code = normaliseLanguage(user?.preferred_language);
    if (code && code !== i18n.language) i18n.changeLanguage(code);
  }, [user]);

  async function loadUser() {
    try {
      const { data } = await api.get('/users/me');
      setUser(data);
    } catch {
      localStorage.removeItem('token');
    } finally {
      setLoading(false);
    }
  }

  async function login(email, password) {
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);
    const { data } = await api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    localStorage.setItem('token', data.access_token);
    // Refresh token is now stored in httpOnly cookie by backend
    api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
    await loadUser();
  }

  async function loginWithOIDC(provider, idToken) {
    // Exchange the PROVIDER's own ID token (Google / Apple) for app JWTs. No
    // Firebase in the path: the backend verifies the token against the
    // provider's published JWKS.
    const { data } = await api.post('/auth/oidc', { provider, id_token: idToken });
    localStorage.setItem('token', data.access_token);
    api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
    await loadUser();
  }

  // There is no one-step web registration any more. `/auth/register` still
  // exists for the shipped mobile builds, but every web signup goes through
  // SignupFlow — details, payment, then the account — so a helper here that
  // creates an unpaid account is a path nobody should be able to take by
  // accident.

  async function refreshToken() {
    // Cookie is sent automatically via withCredentials
    const { data } = await api.post('/auth/refresh');
    localStorage.setItem('token', data.access_token);
    api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
    return data.access_token;
  }

  async function requestPasswordReset(email) {
    const { data } = await api.post('/auth/password-reset/request', { email });
    return data;
  }

  async function confirmPasswordReset(token, newPassword) {
    const { data } = await api.post('/auth/password-reset/confirm', {
      token,
      new_password: newPassword,
    });
    return data;
  }

  function logout() {
    localStorage.removeItem('token');
    delete api.defaults.headers.common.Authorization;
    setUser(null);
    // httpOnly cookie cleared by browser on expiry or explicit backend call
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        loginWithOIDC,
        logout,
        refreshToken,
        requestPasswordReset,
        confirmPasswordReset,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
