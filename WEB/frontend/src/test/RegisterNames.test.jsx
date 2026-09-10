import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const register = vi.fn();
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ register }) }));
vi.mock('../services/api', () => ({
  default: { post: vi.fn(), get: vi.fn(), defaults: { headers: { common: {} } },
             interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } } },
}));

import Register from '../pages/Register';

const draw = () => render(<MemoryRouter><Register /></MemoryRouter>);

const fill = (label, value) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe('Register asks for two names', () => {
  beforeEach(() => { register.mockReset(); register.mockResolvedValue({}); });

  it('offers First Name and Last Name, not a single Full Name', () => {
    draw();
    expect(screen.getByLabelText('First Name')).toBeTruthy();
    expect(screen.getByLabelText('Last Name')).toBeTruthy();
    expect(screen.queryByLabelText('Full Name')).toBeNull();
  });

  it('sends the two parts, so nothing downstream has to guess the surname', async () => {
    draw();
    fill('First Name', 'Adaeze');
    fill('Last Name', 'Okafor');
    fill('Email', 'ada@example.com');
    fill('Date of Birth', '1990-01-01');
    fireEvent.change(document.getElementById('register-password'), { target: { value: 'SecureP@ss1' } });
    fireEvent.submit(screen.getByRole('button', { name: /create|sign up|register/i }).closest('form'));
    await waitFor(() => expect(register).toHaveBeenCalled());
    expect(register.mock.calls[0][2]).toEqual({ firstName: 'Adaeze', lastName: 'Okafor' });
  });

  it('names WHICH field is too short — "name is required" leaves two boxes to guess between', async () => {
    draw();
    fill('First Name', 'Ad');
    fill('Last Name', 'Okafor');
    fill('Email', 'ada@example.com');
    fill('Date of Birth', '1990-01-01');
    fireEvent.change(document.getElementById('register-password'), { target: { value: 'SecureP@ss1' } });
    fireEvent.submit(screen.getByRole('button', { name: /create|sign up|register/i }).closest('form'));
    await waitFor(() => expect(screen.getByText(/First name must be at least 3/i)).toBeTruthy());
    expect(register).not.toHaveBeenCalled();
  });

  it('applies the same rule to the last name', async () => {
    draw();
    fill('First Name', 'Adaeze');
    fill('Last Name', 'Ok');
    fill('Email', 'ada@example.com');
    fill('Date of Birth', '1990-01-01');
    fireEvent.change(document.getElementById('register-password'), { target: { value: 'SecureP@ss1' } });
    fireEvent.submit(screen.getByRole('button', { name: /create|sign up|register/i }).closest('form'));
    await waitFor(() => expect(screen.getByText(/Last name must be at least 3/i)).toBeTruthy());
    expect(register).not.toHaveBeenCalled();
  });
});
