// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

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
  // The module exports AI_TIMEOUT_MS alongside the default client, and the
  // page imports it: reading a PHOTOGRAPH takes about a minute, so the upload
  // cannot run on the 30 s CRUD default. A default-only mock makes every
  // importer throw at load time — Dashboard.test.jsx says the same thing, and
  // this file still broke on it.
  AI_TIMEOUT_MS: 285000,
  default: {
    post: (...args) => postImpl(...args),
    get: (...args) => getImpl(...args),
  },
}));

import PdfTools from '../pages/PdfTools';

const renderPage = () => render(<MemoryRouter><PdfTools /></MemoryRouter>);

async function uploadFile(response = PARSED) {
  postImpl = vi.fn((url) => {
    // The page uploads through the BATCH endpoint now — several documents at
    // once, each staged and routed on its own. A mock is only evidence if it
    // matches the wire (§3at), so this returns the batch envelope rather than
    // the single-document body the page no longer asks for.
    if (url.includes('parse-documents')) {
      return Promise.resolve({ data: {
        documents: [{ filename: 'labs.pdf', ok: true, error: null, document: response }],
        parsed: 1, failed: 0, duplicates: 0,
      } });
    }
    if (url.includes('/confirm')) {
      return Promise.resolve({ data: { import_id: 42, status: 'confirmed', total_imported: 2, message: 'Imported 2 record(s): 2 → lab_results' } });
    }
    if (url.includes('/discard')) {
      return Promise.resolve({ data: {
        import_id: 42, status: 'discarded', removed: { lab_results: 2 }, total_removed: 2,
        message: 'Removed 2 record(s): 2 from lab_results. You can upload this document again to re-import it.',
      } });
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
    expect(postImpl.mock.calls[0][0]).toContain('parse-documents');
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

/* Taking back an import that has ALREADY been written.
 *
 * §3ab's remedy for a bad import is "delete first, then re-import", and until
 * now it had no route through the product: /reject only abandons an import
 * nothing was written from, and this page hid even that button the moment an
 * import succeeded — which is exactly when a misread document gets noticed.
 *
 * This control DELETES clinical rows, so the test that matters most is
 * "asks before deleting anything": a confirm step that still fires the request
 * on the first click is decoration, and decoration on a delete is worse than
 * no confirm at all. */
describe('taking back an import that was already written', () => {
  async function importSomething() {
    await uploadFile();
    await waitFor(() => expect(screen.getByText('Albumin')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Import 2 selected/i }));
    await waitFor(() => expect(screen.getByText(/Imported 2 record/i)).toBeInTheDocument());
  }

  it('is offered only once rows have actually been written', async () => {
    await uploadFile();
    await waitFor(() => expect(screen.getByText('Albumin')).toBeInTheDocument());
    // Nothing is on the record yet, so there is nothing to take back.
    expect(screen.queryByRole('button', { name: /Remove from my records/i })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Import 2 selected/i }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Remove from my records/i })).toBeInTheDocument());
  });

  it('asks before deleting anything', async () => {
    await importSomething();
    const before = postImpl.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: /Remove from my records/i }));

    // The first click only ASKS. Nothing may reach the server.
    expect(postImpl.mock.calls.length).toBe(before);
    expect(screen.getByRole('button', { name: /Keep them/i })).toBeInTheDocument();
  });

  it('deletes only on confirmation, and says what went', async () => {
    await importSomething();
    fireEvent.click(screen.getByRole('button', { name: /Remove from my records/i }));
    fireEvent.click(screen.getByRole('button', { name: /Remove from my records/i }));

    await waitFor(() =>
      expect(postImpl).toHaveBeenCalledWith('/pdf/imports/42/discard'));
    await waitFor(() =>
      expect(screen.getByText(/Removed 2 record/i)).toBeInTheDocument());
  });

  it('keeps the records when the patient backs out', async () => {
    await importSomething();
    fireEvent.click(screen.getByRole('button', { name: /Remove from my records/i }));
    fireEvent.click(screen.getByRole('button', { name: /Keep them/i }));

    expect(postImpl).not.toHaveBeenCalledWith('/pdf/imports/42/discard');
    // …and the way back in is still offered, rather than the page dead-ending.
    expect(screen.getByRole('button', { name: /Remove from my records/i })).toBeInTheDocument();
  });
});

/* ── Several documents at once ────────────────────────────────────────────
 *
 * Operator, 2026-10-15: *"PDF import must support multiple PDF imports at the
 * same time and route them properly."*
 *
 * Each file is its own import on the server; this page reviews ONE at a time
 * with a switcher. The hazard worth testing is bleed — one document's ticks,
 * outcome or rows appearing under another, which would have the patient
 * confirming rows against the wrong report.
 */

const SECOND = {
  ...PARSED,
  import_id: 77,
  patient_name: 'Dana Rivera',
  report_date: '2026-06-02',
  items: [{
    item_id: 9, test_name: 'Potassium', value: '5.9', unit: 'mEq/L',
    reference_range: '3.5 – 5.5', is_abnormal: true, test_date: '2026-06-02',
    dedupe_status: 'new', accepted: true, source_label: 'POTASSIUM', note: null,
  }],
};

async function uploadMany(documents) {
  postImpl = vi.fn((url) => {
    if (url.includes('parse-documents')) {
      return Promise.resolve({ data: {
        documents,
        parsed: documents.filter(d => d.ok).length,
        failed: documents.filter(d => !d.ok).length,
        duplicates: 0,
      } });
    }
    if (url.includes('/confirm')) {
      return Promise.resolve({ data: { import_id: 42, status: 'confirmed',
        total_imported: 1, message: 'Imported 1 record(s)' } });
    }
    return Promise.resolve({ data: {} });
  });
  renderPage();
  const input = document.querySelector('input[type="file"]');
  fireEvent.change(input, { target: { files: [
    new File(['a'], 'march.pdf', { type: 'application/pdf' }),
    new File(['b'], 'june.pdf', { type: 'application/pdf' }),
  ] } });
  fireEvent.click(screen.getByRole('button', { name: /Read Document/i }));
  await waitFor(() => expect(postImpl).toHaveBeenCalled());
}

describe('several documents in one upload', () => {
  it('sends them in ONE request to the batch endpoint', async () => {
    await uploadMany([
      { filename: 'march.pdf', ok: true, error: null, document: PARSED },
      { filename: 'june.pdf', ok: true, error: null, document: SECOND },
    ]);
    expect(postImpl).toHaveBeenCalledTimes(1);
    expect(postImpl.mock.calls[0][0]).toContain('parse-documents');
  });

  it('offers a tab per document, named by its file', async () => {
    await uploadMany([
      { filename: 'march.pdf', ok: true, error: null, document: PARSED },
      { filename: 'june.pdf', ok: true, error: null, document: SECOND },
    ]);
    expect(await screen.findByRole('button', { name: /march\.pdf/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /june\.pdf/ })).toBeInTheDocument();
  });

  it('shows ONE document at a time, and switching changes the rows', async () => {
    await uploadMany([
      { filename: 'march.pdf', ok: true, error: null, document: PARSED },
      { filename: 'june.pdf', ok: true, error: null, document: SECOND },
    ]);
    // The first document's rows, and not the second's.
    await waitFor(() => expect(screen.getByText('Albumin')).toBeInTheDocument());
    expect(screen.queryByText('Potassium')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /june\.pdf/ }));
    await waitFor(() => expect(screen.getByText('Potassium')).toBeInTheDocument());
    // …and the first document's rows are gone, not stacked underneath.
    expect(screen.queryByText('Albumin')).not.toBeInTheDocument();
  });

  it('confirms against the ACTIVE document, not the first one', async () => {
    await uploadMany([
      { filename: 'march.pdf', ok: true, error: null, document: PARSED },
      { filename: 'june.pdf', ok: true, error: null, document: SECOND },
    ]);
    fireEvent.click(screen.getByRole('button', { name: /june\.pdf/ }));
    await waitFor(() => expect(screen.getByText('Potassium')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Import \d+ selected/i }));

    await waitFor(() => {
      const confirmCall = postImpl.mock.calls.find(c => String(c[0]).includes('/confirm'));
      expect(confirmCall).toBeTruthy();
      // 77, not 42 — confirming the document on screen.
      expect(confirmCall[0]).toContain('77');
      expect(confirmCall[1].accepted_item_ids).toEqual([9]);
    });
  });

  it('a file that could not be read says WHY, and the others still import', async () => {
    await uploadMany([
      { filename: 'march.pdf', ok: true, error: null, document: PARSED },
      { filename: 'IMG_0551.jpeg', ok: false, document: null,
        error: 'This looks like a photo (JPEG), not a PDF or text document.' },
    ]);
    // It opens on the document that PARSED, not on the error.
    await waitFor(() => expect(screen.getByText('Albumin')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /IMG_0551\.jpeg/ }));
    await waitFor(() =>
      expect(screen.getByText(/looks like a photo/i)).toBeInTheDocument());
    // An empty review panel here would read as "this document contained
    // nothing", which is the opposite of what happened (§3aa).
    expect(screen.queryByText('Albumin')).not.toBeInTheDocument();
  });
});
