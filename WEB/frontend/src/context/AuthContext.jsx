import { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

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

  async function loginWithFirebase(idToken) {
    // Exchange a Firebase Auth ID token (phone / Google / Apple) for app JWTs.
    const { data } = await api.post('/auth/firebase', { id_token: idToken });
    localStorage.setItem('token', data.access_token);
    api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
    await loadUser();
  }

  async function register(email, password, fullName, phone, dateOfBirth, country) {
    // date_of_birth is REQUIRED by the backend: an account holder must be an
    // adult by their own jurisdiction's standard (app/core/age_policy.py), and
    // `country` selects that threshold — absent, the strictest (16) applies.
    await api.post('/auth/register', {
      email,
      password,
      full_name: fullName,
      phone: phone || null,
      date_of_birth: dateOfBirth,
      country: country || null,
    });
    await login(email, password);
  }

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
        loginWithFirebase,
        register,
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
