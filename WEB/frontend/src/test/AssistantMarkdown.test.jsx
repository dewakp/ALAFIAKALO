import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import AssistantMarkdown from '../components/AssistantMarkdown';

// The real reply from the AI Health Assistant, which rendered as a wall of
// text: bold markers and a full markdown table dumped verbatim into a bubble.
const REAL_REPLY =
  '**Short answer:** The meal is generally okay, but the 1 ripe plantain adds a ' +
  'fairly large amount of potassium. **What to keep in mind** | What | Why it ' +
  'matters for you | How this meal fits | |------|--------------|-----------|| ' +
  '**Potassium** | Your recent lab shows potassium 4.4 mg/dL. | 1 ripe plantain ' +
  '≈400 mg K. | | **Phosphorus** | Your phosphorus is 4.8 mg/dL. | Eggs provide ' +
  '~12 mg P. | **Practical suggestion** - Skip the plantain - Keep olives to 1–2 ' +
  'pieces **Bottom line:** The meal is safe if you cut the plantain.';

describe('AssistantMarkdown', () => {
  it('never shows raw markdown syntax to the reader', () => {
    const { container } = render(<AssistantMarkdown content={REAL_REPLY} />);
    const text = container.textContent;
    expect(text).not.toContain('**');
    // A run of table pipes and dashes is the wall-of-text signature.
    expect(text).not.toMatch(/\|\s*-{3,}/);
    expect(text).not.toContain('|------');
  });

  it('keeps the clinical content intact', () => {
    const { container } = render(<AssistantMarkdown content={REAL_REPLY} />);
    const text = container.textContent;
    for (const fragment of ['Potassium', '400 mg K', 'Phosphorus', '4.8 mg/dL', 'Bottom line']) {
      expect(text).toContain(fragment);
    }
  });

  it('promotes a bold-only line to a heading', () => {
    render(<AssistantMarkdown content={'**Bottom line:**\nEat it.'} />);
    expect(screen.getByText('Bottom line')).toBeInTheDocument();
  });

  it('renders bullets as bullets, not dashes in prose', () => {
    const { container } = render(
      <AssistantMarkdown content={'- first point\n- second point'} />
    );
    expect(container.textContent).toContain('first point');
    expect(container.textContent).not.toContain('- first');
  });

  it('emits no HTML from model text — it is untrusted', () => {
    const { container } = render(
      <AssistantMarkdown content={'<img src=x onerror=alert(1)> **hi**'} />
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
  });

  it('renders nothing for empty content rather than throwing', () => {
    const { container } = render(<AssistantMarkdown content={''} />);
    expect(container.textContent).toBe('');
  });
});
