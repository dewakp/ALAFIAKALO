import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

/* The compose form asked for "Member IDs (comma-separated)" with the
   placeholder "e.g. 14, 15". A member id is an internal handle — nobody knows
   their nephrologist's primary key, so the field was only usable by someone
   reading the database. These tests pin the replacement: search by name, email
   or phone, and never surface a raw id. */

let getImpl, postImpl;
vi.mock('../services/api', () => ({
  default: {
    get: (...args) => getImpl(...args),
    post: (...args) => postImpl(...args),
  },
}));

import { CreateConversationModal } from '../pages/Messaging';

const DOCTOR = {
  id: 42, full_name: 'Adeyemi Nephrologist', email: null,
  email_hint: 'a•••@example.com', phone_hint: null,
  matched_on: 'name', connected: true,
};

const renderModal = (props = {}) => render(
  <CreateConversationModal
    defaultType="direct" typeLocked onClose={() => {}} onCreated={() => {}} {...props} />
);

beforeEach(() => {
  getImpl = vi.fn(() => Promise.resolve({ data: [DOCTOR] }));
  postImpl = vi.fn(() => Promise.resolve({ data: { id: 7 } }));
});

describe('new conversation form', () => {
  it('does not ask the user for member ids', () => {
    renderModal();
    expect(screen.queryByText(/Member ID/i)).toBeNull();
    expect(screen.queryByPlaceholderText(/14, 15/)).toBeNull();
    expect(screen.getByPlaceholderText(/name, email or phone/i)).toBeTruthy();
  });

  it('hides the type dropdown when the tab already chose the type', async () => {
    // A clinical conversation still has its own Priority dropdown, so this
    // asserts the Type field specifically rather than "no combobox".
    renderModal({ defaultType: 'clinical', typeLocked: true });
    expect(screen.getByText('Clinical')).toBeTruthy();
    expect(screen.queryByText('Type')).toBeNull();

    await userEvent.click(screen.getByText('Change'));
    expect(screen.getByText('Type')).toBeTruthy();
  });

  it('offers the dropdown when arriving from the All tab', () => {
    renderModal({ typeLocked: false });
    expect(screen.getByText('Type')).toBeTruthy();
  });

  it('searches by name and sends the id it resolved', async () => {
    const onCreated = vi.fn();
    renderModal({ onCreated });

    await userEvent.type(screen.getByPlaceholderText(/name, email or phone/i), 'Adeyemi');
    await waitFor(() => expect(getImpl).toHaveBeenCalledWith(
      '/messaging/recipients', { params: { q: 'Adeyemi' } }));

    await userEvent.click(await screen.findByText('Adeyemi Nephrologist'));
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(postImpl).toHaveBeenCalledWith(
      '/messaging/conversations', expect.objectContaining({ member_ids: [42] })));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
  });

  it('refuses to create a conversation with nobody in it', async () => {
    renderModal();
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(await screen.findByText(/Choose who to message/i)).toBeTruthy();
    expect(postImpl).not.toHaveBeenCalled();
  });

  it('says a failed search failed, instead of "nobody found"', async () => {
    // An error is not an empty state: reporting "nobody found" would send the
    // user hunting for a contact who is in fact right there.
    getImpl = vi.fn(() => Promise.reject({ response: { status: 500 } }));
    renderModal();

    await userEvent.type(screen.getByPlaceholderText(/name, email or phone/i), 'Adeyemi');
    expect(await screen.findByText(/Could not search right now/i)).toBeTruthy();
    expect(screen.queryByText(/Nobody found/i)).toBeNull();
  });

  it('surfaces the server error rather than silently doing nothing', async () => {
    postImpl = vi.fn(() => Promise.reject({ response: { data: { detail: 'No active user for member id(s): [99]' } } }));
    renderModal();

    await userEvent.type(screen.getByPlaceholderText(/name, email or phone/i), 'Adeyemi');
    await userEvent.click(await screen.findByText('Adeyemi Nephrologist'));
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText(/No active user for member id/i)).toBeTruthy();
  });
});
