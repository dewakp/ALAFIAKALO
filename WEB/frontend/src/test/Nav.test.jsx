import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/api', () => ({
  default: { get: vi.fn(() => Promise.resolve({ data: { count: 0 } })) },
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: null, logout: vi.fn() }),
  AuthProvider: ({ children }) => children,
}));

import Layout from '../components/Layout';
import { MarketingNav, MarketingFooter } from '../components/MarketingChrome';

const SUPPORT_LINKS = [
  ['Help', '/help'],
  ['Contact Us', '/contact'],
  ['Investors', '/investors'],
];

describe('marketing footer', () => {
  it('links to Help, Contact Us and Investors', () => {
    render(<MemoryRouter><MarketingFooter /></MemoryRouter>);
    for (const [label, href] of SUPPORT_LINKS) {
      expect(screen.getByRole('link', { name: label })).toHaveAttribute('href', href);
    }
  });
});

describe('marketing nav', () => {
  it('keeps the support links out of the navbar', () => {
    render(<MemoryRouter><MarketingNav /></MemoryRouter>);
    for (const [label] of SUPPORT_LINKS) {
      expect(screen.queryByRole('link', { name: label })).toBeNull();
    }
  });

  it('makes the landing section anchors absolute when rendered off the landing page', () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/landing']}><MarketingNav /></MemoryRouter>
    );
    expect(screen.getByRole('link', { name: 'Features' })).toHaveAttribute('href', '#features');
    unmount();

    render(<MemoryRouter initialEntries={['/help']}><MarketingNav /></MemoryRouter>);
    expect(screen.getByRole('link', { name: 'Features' })).toHaveAttribute('href', '/landing#features');
  });
});

describe('in-app sidebar footer', () => {
  it('links to Help, Contact Us and Investors', () => {
    render(<MemoryRouter><Layout /></MemoryRouter>);

    const footer = document.querySelector('.sidebar-footer-links');
    for (const [label, href] of SUPPORT_LINKS) {
      expect(within(footer).getByRole('link', { name: label })).toHaveAttribute('href', href);
    }
  });
});
