// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Privacy renders inside MarketingChrome, which brings two jsdom problems that
// have nothing to do with the policy: MarketingNav calls useAuth() and throws
// outside a provider, and SnowCanvas animates on a <canvas> whose getContext('2d')
// returns null in jsdom, so the draw loop throws inside the effect and takes the
// whole render with it. LandingBeta.test.jsx stubs the chrome for the same reason.
//
// That file mocks only the NAMED exports; Privacy imports MarketingPage as the
// module's DEFAULT, so the default is what has to be replaced here — a mock
// without it renders nothing and fails for an unrelated reason.
vi.mock('../components/MarketingChrome', () => ({
  default: ({ children }) => children,
}));

import Privacy from '../pages/Privacy';

/**
 * The public privacy policy is the Privacy Policy URL registered with App Store
 * Connect and Google Play, and iOS links straight to it (AIAndDataView and
 * DashboardView both open https://alafia.app/privacy). So this page is the ONE
 * place the operating company is stated to a patient on any platform.
 *
 * It named no company at all until 2026-09-26: 67 strings, not one saying who
 * runs the service. A policy that never identifies its data controller is the
 * §3aa failure applied to legal copy — the page looks complete and answers the
 * one question a regulator asks with silence.
 *
 * These assertions exist so that statement cannot disappear in a refactor
 * without a test going red.
 */
describe('Privacy policy', () => {
  it('names 6igma Health Inc as the operating company and data controller', () => {
    render(
      <MemoryRouter>
        <Privacy />
      </MemoryRouter>
    );

    expect(screen.getByText('Who operates ALAFIA')).toBeInTheDocument();

    // Matched by substring rather than the whole sentence: the wording may be
    // edited, but the COMPANY and its ROLE are the facts under test.
    //
    // The name is pinned WITH "Inc". ALAFIA is the PRODUCT; 6igma Health Inc is
    // the legal entity, and the App Store Connect seller name, the iOS bundle's
    // NSHumanReadableCopyright, the web footer and this page must all state the
    // same one. Apple rejected 1.5(10) under 5.1.1(ix) precisely because the
    // publisher was not identifiable, so a refactor that shortens this to the
    // brand re-opens that rejection silently. Matching /6igma Health/ would
    // still pass with "Inc" gone; this fails on the missing suffix.
    const statement = screen.getByText(/6igma Health Inc/);
    expect(statement).toBeInTheDocument();
    expect(statement.textContent).toMatch(/data controller/i);
  });

  it('still renders the sections a policy is required to have', () => {
    render(
      <MemoryRouter>
        <Privacy />
      </MemoryRouter>
    );

    expect(screen.getByText('What we collect')).toBeInTheDocument();
    expect(screen.getByText('What we never do')).toBeInTheDocument();
    expect(screen.getByText('Where your data goes')).toBeInTheDocument();
    expect(screen.getByText('Your rights')).toBeInTheDocument();
    expect(screen.getByText('How long we keep it')).toBeInTheDocument();
  });
});
