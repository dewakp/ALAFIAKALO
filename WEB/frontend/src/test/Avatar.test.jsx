import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Avatar, { initialsOf, tintFor } from '../components/Avatar';

describe('Avatar', () => {
  it('renders the photo when there is one', () => {
    render(<Avatar src="data:image/jpeg;base64,AAAA" name="Adaeze Okafor" id={7} />);
    const img = screen.getByRole('img');
    expect(img.getAttribute('src')).toBe('data:image/jpeg;base64,AAAA');
    // Named, not "avatar" — a patient grid of twenty "image" announcements
    // tells a screen-reader user nothing.
    expect(img.getAttribute('alt')).toBe('Adaeze Okafor');
  });

  it('falls back to initials, which is what every account has today', () => {
    const { container } = render(<Avatar name="Adaeze Okafor" id={7} />);
    expect(container.textContent).toBe('AO');
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('never renders an empty circle for a missing name', () => {
    const { container } = render(<Avatar id={0} />);
    expect(container.textContent).toBe('?');
  });

  it('takes at most two initials, so a long name does not overflow', () => {
    expect(initialsOf('Olorunfemi Oluwabunmi Cecilia Adeyemi')).toBe('OO');
  });

  it('keeps a person the same colour between loads', () => {
    expect(tintFor(42)).toBe(tintFor(42));
    // A non-numeric or absent id must not throw — it lands on the first tint.
    expect(tintFor(undefined)).toBe(tintFor(0));
  });
});
