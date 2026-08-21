import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import api from '../services/api';
import ICD11Picker from '../components/ICD11Picker';
import ChronicConditions from '../pages/ChronicConditions';

const CKD = {
  code: 'GB61.5',
  title: 'Chronic kidney disease, stage 5',
  chapter: '16',
  chapter_title: 'Diseases of the genitourinary system',
  is_leaf: true,
  is_residual: false,
};

function searchOk(results) {
  return Promise.resolve({ data: { query: 'x', results, total: results.length } });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ICD11Picker', () => {
  it('searches what the patient typed and reports the selection upward', async () => {
    const user = userEvent.setup();
    api.get.mockImplementation(() => searchOk([CKD]));
    const onChange = vi.fn();

    render(<ICD11Picker code="" title="" onChange={onChange} />);
    await user.type(screen.getByRole('combobox'), 'ESRD');

    const option = await screen.findByRole('option', { name: /Chronic kidney disease, stage 5/ });
    expect(api.get).toHaveBeenCalledWith(
      '/chronic/icd11/search',
      expect.objectContaining({ params: expect.objectContaining({ q: 'ESRD' }) }),
    );

    await user.click(option);
    // The title comes back with the code so the row can display it without a
    // second round-trip; the backend still re-derives it on save.
    expect(onChange).toHaveBeenCalledWith({
      code: 'GB61.5',
      title: 'Chronic kidney disease, stage 5',
    });
  });

  it('shows a failed lookup as an error, never as "no match"', async () => {
    const user = userEvent.setup();
    api.get.mockRejectedValue({ response: { status: 500 } });

    render(<ICD11Picker code="" title="" onChange={vi.fn()} />);
    await user.type(screen.getByRole('combobox'), 'kidney');

    // This is the §3aa failure in miniature: an unreachable catalog must not
    // tell the patient their condition does not exist.
    expect(await screen.findByTestId('icd11-error')).toBeInTheDocument();
    expect(screen.queryByTestId('icd11-empty')).toBeNull();
  });

  it('distinguishes a genuinely empty result from an error', async () => {
    const user = userEvent.setup();
    api.get.mockImplementation(() => searchOk([]));

    render(<ICD11Picker code="" title="" onChange={vi.fn()} />);
    await user.type(screen.getByRole('combobox'), 'zzzzz');

    expect(await screen.findByTestId('icd11-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('icd11-error')).toBeNull();
  });

  it('renders a chosen code as a clearable chip instead of the search box', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<ICD11Picker code="GB61.5" title="Chronic kidney disease, stage 5" onChange={onChange} />);
    expect(screen.getByTestId('icd11-selected')).toHaveTextContent('GB61.5');
    expect(screen.queryByRole('combobox')).toBeNull();

    await user.click(screen.getByRole('button', { name: /Remove ICD-11 code GB61.5/ }));
    expect(onChange).toHaveBeenCalledWith({ code: '', title: '' });
  });

  it('does not fire a request for an empty query', async () => {
    const user = userEvent.setup();
    api.get.mockImplementation(() => searchOk([CKD]));

    render(<ICD11Picker code="" title="" onChange={vi.fn()} />);
    await user.click(screen.getByRole('combobox'));
    await new Promise((r) => setTimeout(r, 350));

    expect(api.get).not.toHaveBeenCalled();
  });
});

describe('ChronicConditions page', () => {
  it('lists conditions with both coding systems', async () => {
    api.get.mockResolvedValue({
      data: [
        {
          id: 1,
          condition_name: 'End-Stage Renal Disease (ESRD)',
          category: 'renal',
          severity: 'severe',
          is_active: true,
          icd10_code: 'N18.6',
          icd11_code: 'GB61.5',
          icd11_title: 'Chronic kidney disease, stage 5',
        },
      ],
    });

    render(<MemoryRouter><ChronicConditions /></MemoryRouter>);

    expect(await screen.findByText(/End-Stage Renal Disease/)).toBeInTheDocument();
    // Both are shown and labelled: an ICD-10 read off an imported document and
    // an ICD-11 the patient chose are different facts, not duplicates.
    expect(screen.getByText(/ICD-11: GB61.5/)).toBeInTheDocument();
    expect(screen.getByText(/ICD-10: N18.6/)).toBeInTheDocument();
  });

  it('does not render a failed load as "no conditions recorded"', async () => {
    api.get.mockRejectedValue(new Error('boom'));

    render(<MemoryRouter><ChronicConditions /></MemoryRouter>);

    await waitFor(() =>
      expect(screen.getByTestId('conditions-load-error')).toBeInTheDocument(),
    );
    expect(screen.queryByText(/No chronic conditions recorded yet/)).toBeNull();
  });

  it('shows an empty list as empty', async () => {
    api.get.mockResolvedValue({ data: [] });

    render(<MemoryRouter><ChronicConditions /></MemoryRouter>);

    expect(await screen.findByText(/No chronic conditions recorded yet/)).toBeInTheDocument();
    expect(screen.queryByTestId('conditions-load-error')).toBeNull();
  });
});
