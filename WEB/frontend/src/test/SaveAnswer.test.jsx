/**
 * An answer you can keep.
 *
 * The record existed all along — every exchange is written to
 * `ai_interactions` — but nothing read it back, so an answer vanished when the
 * screen changed and a patient who wanted to show a clinician what the
 * assistant said had nothing to show.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const post = vi.fn(() => Promise.resolve({ data: { saved: true } }));
const del = vi.fn(() => Promise.resolve({ data: { saved: false } }));
vi.mock('../services/api', () => ({ default: { post: (...a) => post(...a), delete: (...a) => del(...a) } }));

import SaveAnswer from '../components/SaveAnswer';

describe('SaveAnswer', () => {
  beforeEach(() => { post.mockClear(); del.mockClear(); });

  it('renders nothing when there is no interaction to point at', () => {
    const { container } = render(<SaveAnswer interactionId={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('saves an answer', async () => {
    render(<SaveAnswer interactionId={7} />);
    await userEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/ai/history/7/save'));
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true');
  });

  it('removes a save', async () => {
    render(<SaveAnswer interactionId={7} initiallySaved />);
    await userEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/ai/history/7/save'));
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false');
  });

  it('says it failed instead of pretending it saved', async () => {
    post.mockRejectedValueOnce(new Error('offline'));
    render(<SaveAnswer interactionId={7} />);
    await userEvent.click(screen.getByRole('button'));
    // Flipping the icon on a failed request is a lie about something the
    // patient is relying on being able to find again.
    await waitFor(() => expect(screen.getByText('Not saved')).toBeInTheDocument());
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false');
  });
});
