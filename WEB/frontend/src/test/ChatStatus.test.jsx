/**
 * The wait is the feature here.
 *
 * The tool rounds take tens of seconds and cannot stream, so the assistant
 * bubble is empty for the whole time. It used to show a blinking cursor, which
 * cannot tell a working request from a hung one.
 *
 * These frames are REPORTS from the server, not a reassuring animation: the
 * component must show what it was told and nothing else.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ChatStatus from '../components/ChatStatus';

describe('ChatStatus', () => {
  it('shows the label the server sent', () => {
    render(<ChatStatus step={{ label: 'Checking your meals', phase: 'tool' }} />);
    expect(screen.getByText(/Checking your meals/)).toBeInTheDocument();
  });

  it('shows the row count beside the label when one came back', () => {
    render(<ChatStatus step={{ label: 'Checking your meals', detail: '6 found' }} />);
    expect(screen.getByText(/6 found/)).toBeInTheDocument();
  });

  it('says something true before the first frame arrives', () => {
    // Falling back to empty would reinstate the blank wait this exists to fix.
    render(<ChatStatus step={null} />);
    expect(screen.getByRole('status')).toHaveTextContent(/Querying AI/);
  });

  it('is announced to assistive tech as a live region', () => {
    render(<ChatStatus step={{ label: 'Checking your labs' }} />);
    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('aria-live', 'polite');
  });

  it('never invents a step that was not reported', () => {
    render(<ChatStatus step={{ label: 'Checking your medications' }} />);
    expect(screen.queryByText(/meals/i)).toBeNull();
    expect(screen.queryByText(/labs/i)).toBeNull();
  });
});
