import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/* The import flow's whole point is that nothing is written until the patient
   agrees. These tests pin that boundary, plus the two states the old page got
   wrong: a failed parse rendering as an empty table, and duplicates being
   pre-selected for import. */

const PARSED = {
  import_id: 42,
  doc_type: 'lab_report',
  target_table: 'lab_results',
  confidence: 0.82,
  patient_name: 'Dana Rivera',
  report_date: '2026-03-14',
  lab_name: 'Riverside Labs',
  ordering_physician: 'Okafor, N MD',
  raw_text_preview: 'Lab Draw Report…',
  parsing_notes: [],
  error: null,
  already_imported: false,
  items: [
    {
      item_id: 1, test_name: 'Albumin', value: '4.6', unit: 'g/dL',
      reference_range: '3.4 – 4.8', is_abnormal: false, test_date: '2026-03-14',
      dedupe_status: 'new', accepted: true, source_label: 'ALBUMIN', note: null,
    },
    {
      item_id: 2, test_name: 'Alk Phos', value: '637', unit: 'U/L',
      reference_range: '46 – 116', is_abnormal: true, test_date: '2026-03-14',
      dedupe_status: 'new', accepted: true, source_label: 'ALK PHOS', note: null,
    },
    {
      item_id: 3, test_name: 'Calcium', value: '9.1', unit: 'mg/dL',
      reference_range: '8.7 – 10.4', is_abnormal: false, test_date: '2026-03-14',
      dedupe_status: 'duplicate', accepted: false, source_label: 'CALCIUM', note: null,
    },
  ],
};

let postImpl;
let getImpl;
vi.mock('../services/api', () => ({
  default: {
    post: (...args) => postImpl(...args),
    get: (...args) => getImpl(...args),
  },
}));

import PdfTools from '../pages/PdfTools';

const renderPage = () => render(<MemoryRouter><PdfTools /></MemoryRouter>);

async function uploadFile(response = PARSED) {
  postImpl = vi.fn((url) => {
    if (url.includes('parse-document')) return Promise.resolve({ data: response });
    if (url.includes('/confirm')) {
      return Promise.resolve({ data: { import_id: 42, status: 'confirmed', total_imported: 2, message: 'Imported 2 record(s): 2 → lab_results' } });
    }
    return Promise.resolve({ data: {} });
  });
  renderPage();

  const input = document.querySelector('input[type="file"]');
  const file = new File(['x'], 'labs.pdf', { type: 'application/pdf' });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: /Read Document/i }));
  await waitFor(() => expect(postImpl).toHaveBeenCalled());
}

beforeEach(() => {
  getImpl = vi.fn(() => Promise.resolve({ data: {} }));
});

describe('document import review', () => {
  it('reads the document without writing anything', async () => {
    await uploadFile();
    await waitFor(() => expect(screen.getByText('Albumin')).toBeInTheDocument());

    // Only the parse call — no confirm was sent.
    expect(postImpl).toHaveBeenCalledTimes(1);
    expect(postImpl.mock.calls[0][0]).toContain('parse-document');
  });

  it('shows the readings with their ranges', async () => {
    await uploadFile();
    await waitFor(() => expect(screen.getByText('Albumin')).toBeInTheDocument());
    expect(screen.getByText('3.4 – 4.8')).toBeInTheDocument();
    expect(screen.getByText('Alk Phos')).toBeInTheDocument();
  });

  it('marks an out-of-range result as abnormal', async () => {
    await uploadFile();
    await waitFor(() => expect(screen.getAllByText(/Abnormal/i).length).toBe(1));
  });

  it('does not pre-select a reading already on file', async () => {
    await uploadFile();
    await waitFor(() => expect(screen.getByText('Calcium')).toBeInTheDocument());

    expect(screen.getByText(/Already recorded/i)).toBeInTheDocument();
    // Two of three staged rows are ticked; the duplicate is not.
    expect(screen.getByText(/2 selected to import/i)).toBeInTheDocument();
  });

  it('imports only the selected rows when confirmed', async () => {
    await uploadFile();
    await waitFor(() => expect(screen.getByText('Albumin')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /Import 2 selected/i }));
    await waitFor(() =>
      expect(postImpl).toHaveBeenCalledWith('/pdf/imports/42/confirm', { accepted_item_ids: [1, 2] })
    );
    await waitFor(() => expect(screen.getByText(/Imported 2 record/i)).toBeInTheDocument());
  });

  it('surfaces a parse failure instead of an empty table', async () => {
    await uploadFile({
      ...PARSED,
      items: [],
      target_table: null,
      error: 'This PDF has no selectable text — text recognition (OCR) is required to read it.',
    });
    await waitFor(() =>
      expect(screen.getByText(/text recognition \(OCR\) is required/i)).toBeInTheDocument()
    );
  });

  it('says when a file was uploaded before', async () => {
    await uploadFile({ ...PARSED, already_imported: true });
    await waitFor(() =>
      expect(screen.getByText(/uploaded this file before/i)).toBeInTheDocument()
    );
  });

  it('shows what the document called a test when it was renamed', async () => {
    await uploadFile();
    await waitFor(() => expect(screen.getByText(/document: “ALBUMIN”/)).toBeInTheDocument());
  });
});
