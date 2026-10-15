// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

import { useState } from 'react';
import api from '../services/api';
import { FileText, Download, Upload, FileBarChart, Check, X, AlertTriangle } from 'lucide-react';
import BackButton from '../components/BackButton';
import { t } from '../i18n';

const tabs = [
  { key: 'import', get label() { return t('PdfTools.import_document'); }, icon: Upload },
  { key: 'flowsheet', get label() { return t('PdfTools.generate_flowsheet'); }, icon: FileBarChart },
];

export default function PdfTools() {
  const [activeTab, setActiveTab] = useState('import');

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">{t('PdfTools.pdf_tools')}</h1>
        </div>
      </div>
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        {tabs.map(({ key, label, icon: Icon }) => (
          <button key={key} className={`btn ${activeTab === key ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab(key)}>
            <Icon size={16} /> {label}
          </button>
        ))}
      </div>
      {activeTab === 'import' && <ImportDocument />}
      {activeTab === 'flowsheet' && <GenerateFlowsheet />}
    </div>
  );
}

const DEDUPE_BADGE = {
  duplicate: { get text() { return t('PdfTools.already_recorded'); }, bg: '#e5e7eb', fg: '#4b5563' },
  conflict: { get text() { return t('PdfTools.differs_from_existing'); }, bg: '#fef3c7', fg: '#b45309' },
};

const EMPTY_SET = new Set();

const DOC_TYPE_LABEL = {
  lab_report: 'Lab report',
  medication_list: 'Medication list',
  discharge_summary: 'Discharge summary',
  dialysis_flowsheet: 'Dialysis flowsheet',
  imaging_report: 'Imaging report',
  unknown: 'Unrecognised document',
};

function ImportDocument() {
  /* Several documents at once (operator, 2026-10-15), each staged and routed
     on its own — the server returns one `import_id` per file and confirm,
     reject and discard all stay per-document.

     The REVIEW surface is deliberately still one document at a time, with a
     switcher above it. Five documents' rows in one scroll is worse to use and
     would have meant rewriting 300 lines of review markup; this reuses all of
     it and changes only which document is current. */
  const [files, setFiles] = useState([]);
  const [batch, setBatch] = useState(null);      // [{filename, ok, error, document}]
  const [activeIdx, setActiveIdx] = useState(0);
  /* Per-document, keyed by import_id. A single shared Set would carry one
     document's ticks onto the next one the reviewer opened — confirming rows
     against the wrong report, which is the whole hazard of batching. */
  const [selectedBy, setSelectedBy] = useState({});
  const [importedBy, setImportedBy] = useState({});
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState(null);
  const [showRaw, setShowRaw] = useState(false);
  // Removing a CONFIRMED import deletes clinical rows, so it asks first — two
  // clicks inline rather than a browser dialog, which is untestable and easy to
  // dismiss by reflex.
  const [removing, setRemoving] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removed, setRemoved] = useState(null);

  /* The document under review, and its own ticks and outcome. Everything below
     reads these exactly as it did when the page handled one file. */
  const entry = batch?.[activeIdx] || null;
  const result = entry?.document || null;
  const importId = result?.import_id ?? null;
  const selected = selectedBy[importId] || EMPTY_SET;
  const imported = importedBy[importId] || null;

  const setSelected = (next) => setSelectedBy(prev => ({
    ...prev,
    [importId]: typeof next === 'function' ? next(prev[importId] || EMPTY_SET) : next,
  }));
  const setImported = (value) => setImportedBy(prev => ({ ...prev, [importId]: value }));

  async function handleSubmit(e) {
    e.preventDefault();
    if (!files.length) return;
    setLoading(true);
    setError(null);
    setImportedBy({});
    try {
      const fd = new FormData();
      // Every part is named `files` — that is what makes FastAPI bind a list.
      files.forEach(f => fd.append('files', f));
      const { data } = await api.post('/pdf/parse-documents', fd);
      setBatch(data.documents || []);
      // Open the first document that actually parsed, rather than always the
      // first file: landing on an error card hides the work that succeeded.
      const firstOk = (data.documents || []).findIndex(d => d.ok);
      setActiveIdx(firstOk >= 0 ? firstOk : 0);
      // Pre-tick what the server judged safe to import, PER DOCUMENT —
      // duplicates stay off.
      const ticks = {};
      (data.documents || []).forEach(d => {
        const doc = d.document;
        if (doc?.import_id) {
          ticks[doc.import_id] = new Set(
            (doc.items || []).filter(i => i.accepted).map(i => i.item_id));
        }
      });
      setSelectedBy(ticks);
    } catch (err) {
      setBatch(null);
      setError(err?.response?.data?.detail || 'The documents could not be read.');
    } finally {
      setLoading(false);
    }
  }

  function toggle(id) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function handleImport() {
    if (!importId) return;
    setImporting(true);
    setError(null);
    try {
      const { data } = await api.post(`/pdf/imports/${importId}/confirm`, {
        accepted_item_ids: [...selected],
      });
      setImported(data);
    } catch (err) {
      setError(err?.response?.data?.detail || 'The import could not be completed.');
    } finally {
      setImporting(false);
    }
  }

  /* Drops the ACTIVE document only. The rest of the batch is untouched —
     rejecting one report must not throw away four others the patient has not
     reviewed yet. */
  function dropActive() {
    setBatch(prev => {
      const next = (prev || []).filter((_, i) => i !== activeIdx);
      setActiveIdx(Math.max(0, Math.min(activeIdx, next.length - 1)));
      return next.length ? next : null;
    });
    if (!batch || batch.length <= 1) setFiles([]);
  }

  async function handleDiscard() {
    if (!importId) return;
    try { await api.post(`/pdf/imports/${importId}/reject`); } catch { /* already gone */ }
    dropActive();
  }

  // Take back an import that was ALREADY written. `reject` cannot do this — it
  // marks an import nothing was ever saved from — and until now the only route
  // out of a bad import was somebody running SQL against production (§3ab).
  // Deletes only the rows this document added, by the id recorded against each
  // one at import time; anything the patient typed is untouched.
  async function handleRemove() {
    if (!importId) return;
    setRemoving(true);
    setError(null);
    try {
      const { data } = await api.post(`/pdf/imports/${importId}/discard`);
      setImported(null);
      setConfirmRemove(false);
      setRemoved(data.message);
      dropActive();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Those records could not be removed.');
    } finally {
      setRemoving(false);
    }
  }

  const canImport = result?.target_table && selected.size > 0 && !imported;

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <h3 style={{ marginBottom: '.25rem' }}>{t('PdfTools.import_a_clinical_document')}</h3>
      <p style={{ fontSize: '.82rem', color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>
        {t('PdfTools.upload_a_lab_report_medication_list_or')}
      </p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">{t('PdfTools.document_pdf_or_text')}</label>
          <input type="file" accept=".pdf,.txt" className="form-input" multiple
            onChange={e => {
              setFiles(Array.from(e.target.files || []));
              setBatch(null); setImportedBy({}); setSelectedBy({}); setError(null);
            }} />
          {files.length > 1 && (
            <p style={{ fontSize: '.78rem', color: 'var(--color-text-tertiary)', margin: '.3rem 0 0' }}>
              {t('PdfTools.n_documents_selected', { count: files.length })}
            </p>
          )}
        </div>
        <button className="btn btn-primary" disabled={!files.length || loading}>
          <Upload size={16} /> {(loading) ? t('PdfTools.reading') : t('PdfTools.read_document')}
        </button>
      </form>

      {error && (
        <div style={bannerStyle('#fee2e2', '#fca5a5', '#b91c1c')}>
          <AlertTriangle size={15} /> {error}
        </div>
      )}

      {/* A document that could not be read must say so — an empty table here
          would read as "this document contained no results". */}
      {result?.error && (
        <div style={bannerStyle('#fef3c7', '#fcd34d', '#b45309')}>
          <AlertTriangle size={15} /> {result.error}
        </div>
      )}

      {result?.already_imported && (
        <div style={bannerStyle('#e0f2fe', '#7dd3fc', '#0369a1')}>
          {t('PdfTools.you_have_uploaded_this_file_before')}
        </div>
      )}

      {removed && (
        <div style={bannerStyle('#e0f2fe', '#7dd3fc', '#0369a1')}>
          <Check size={15} /> {removed}
        </div>
      )}

      {imported && (
        <div style={bannerStyle('#dcfce7', '#86efac', '#15803d')}>
          <Check size={15} /> {imported.message}
        </div>
      )}

      {/* The way OUT of a bad import. Offered exactly when it is useful —
          after the rows have been written — which is when someone notices the
          document was misread. Before this, the only route was a DBA. */}
      {imported && result?.import_id && (
        <div style={{ marginTop: '.6rem' }}>
          {!confirmRemove ? (
            <>
              <button className="btn btn-secondary btn-sm" type="button"
                onClick={() => setConfirmRemove(true)}>
                <X size={14} /> {t('PdfTools.remove_from_records')}
              </button>
              <div style={{ fontSize: '.72rem', color: 'var(--color-text-tertiary)', marginTop: '.3rem' }}>
                {t('PdfTools.remove_hint')}
              </div>
            </>
          ) : (
            <div style={bannerStyle('#fef3c7', '#fcd34d', '#b45309')}>
              <AlertTriangle size={15} />
              <span>{t('PdfTools.remove_confirm', { count: imported.total_imported })}</span>
              <button className="btn btn-danger btn-sm" type="button"
                disabled={removing} onClick={handleRemove}>
                {removing ? t('PdfTools.removing') : t('PdfTools.remove_from_records')}
              </button>
              <button className="btn btn-secondary btn-sm" type="button"
                disabled={removing} onClick={() => setConfirmRemove(false)}>
                {t('PdfTools.keep')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* THE BATCH, with one document under review at a time.

          A result a patient cannot attribute to a file is a result they would
          confirm against the wrong report, so every tab carries its filename
          and its own outcome. Failures are shown here rather than hidden: a
          file that could not be read is a finding, and §3ab's rule is that a
          parser dropping what it cannot read without counting it hides its own
          failure. */}
      {batch && batch.length > 1 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.4rem', marginBottom: '1rem' }}>
          {batch.map((d, i) => {
            const active = i === activeIdx;
            const done = d.document?.import_id && importedBy[d.document.import_id];
            return (
              <button
                key={`${d.filename}-${i}`}
                type="button"
                onClick={() => { setActiveIdx(i); setError(null); setConfirmRemove(false); }}
                title={d.error || d.filename}
                style={{
                  padding: '.35rem .6rem', fontSize: '.78rem', borderRadius: 6,
                  cursor: 'pointer', maxWidth: 230, overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  border: `1px solid ${active ? 'var(--color-primary)' : 'var(--color-border)'}`,
                  background: active ? 'var(--color-primary)' : 'var(--color-surface)',
                  color: active ? '#fff' : (d.ok ? 'var(--color-text)' : '#b91c1c'),
                }}
              >
                {d.ok ? (done ? '✓ ' : '') : '⚠ '}{d.filename}
              </button>
            );
          })}
        </div>
      )}

      {/* A document that could not be read says WHY, in its own tab. An empty
          review panel here would read as "this document contained nothing". */}
      {entry && !entry.ok && (
        <div style={bannerStyle('#fee2e2', '#fca5a5', '#b91c1c')}>
          <AlertTriangle size={15} /> {entry.filename}: {entry.error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: '1.25rem' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.25rem', marginBottom: '.75rem', fontSize: '.85rem' }}>
            {result.doc_type && (
              <div><strong>{t('PdfTools.type')}</strong> {DOC_TYPE_LABEL[result.doc_type] || result.doc_type}</div>
            )}
            {result.patient_name && <div><strong>{t('PdfTools.patient')}</strong> {result.patient_name}</div>}
            {result.report_date && <div><strong>{t('PdfTools.date')}</strong> {result.report_date}</div>}
            {result.lab_name && <div><strong>{t('PdfTools.lab')}</strong> {result.lab_name}</div>}
            {result.ordering_physician && <div><strong>{t('PdfTools.physician')}</strong> {result.ordering_physician}</div>}
            {result.confidence != null && (
              <div><strong>{t('PdfTools.confidence')}</strong> {Math.round(result.confidence * 100)}%</div>
            )}
          </div>

          {result.parsing_notes?.length > 0 && (
            <ul style={{ fontSize: '.76rem', color: 'var(--color-text-tertiary)', marginBottom: '.75rem', paddingLeft: '1.1rem' }}>
              {result.parsing_notes.map((note, i) => <li key={i}>{note}</li>)}
            </ul>
          )}

          {result.items?.length > 0 && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '.5rem' }}>
                <strong style={{ fontSize: '.9rem' }}>
                  {(result.items.length === 1) ? t('PdfTools.reading_found', { items: result.items.length, target_table: result.target_table && ` · ${selected.size} selected to import` }) : t('PdfTools.readings_found', { items: result.items.length, target_table: result.target_table && ` · ${selected.size} selected to import` })}
                </strong>
                {!imported && result.target_table && (
                  <div style={{ display: 'flex', gap: '.4rem' }}>
                    <button className="btn btn-secondary btn-sm" type="button"
                      onClick={() => setSelected(new Set(result.items.map(i => i.item_id)))}>
                      {t('PdfTools.select_all')}
                    </button>
                    <button className="btn btn-secondary btn-sm" type="button"
                      onClick={() => setSelected(new Set())}>
                      {t('PdfTools.clear')}
                    </button>
                  </div>
                )}
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '.83rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                      {result.target_table && !imported && <th style={thStyle}></th>}
                      <th style={thStyle}>{t('PdfTools.test')}</th>
                      <th style={thStyle}>{t('PdfTools.value')}</th>
                      <th style={thStyle}>{t('PdfTools.unit')}</th>
                      <th style={thStyle}>{t('PdfTools.reference')}</th>
                      <th style={thStyle}>{t('PdfTools.date_2')}</th>
                      <th style={thStyle}>{t('PdfTools.status')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.items.map(item => (
                      <tr key={item.item_id} style={{
                        borderBottom: '1px solid var(--color-border)',
                        background: item.is_abnormal ? '#fef2f2' : 'transparent',
                      }}>
                        {result.target_table && !imported && (
                          <td style={tdStyle}>
                            <input type="checkbox" checked={selected.has(item.item_id)}
                              onChange={() => toggle(item.item_id)} />
                          </td>
                        )}
                        <td style={tdStyle}>
                          {item.test_name}
                          {item.source_label && item.source_label !== item.test_name && (
                            <div style={{ fontSize: '.68rem', color: 'var(--color-text-tertiary)' }}>
                              {t('PdfTools.document', { source_label: item.source_label })}
                            </div>
                          )}
                          {item.note && (
                            <div style={{ fontSize: '.68rem', color: '#b45309' }}>{item.note}</div>
                          )}
                        </td>
                        <td style={tdStyle}><strong>{item.value ?? '—'}</strong></td>
                        <td style={tdStyle}>{item.unit || '—'}</td>
                        <td style={tdStyle}>{item.reference_range || '—'}</td>
                        <td style={tdStyle}>{item.test_date || '—'}</td>
                        <td style={tdStyle}>
                          {item.is_abnormal && (
                            <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>{t('PdfTools.abnormal')}</span>
                          )}
                          {DEDUPE_BADGE[item.dedupe_status] && (
                            <span style={{
                              marginLeft: item.is_abnormal ? '.35rem' : 0,
                              fontSize: '.68rem', fontWeight: 600, padding: '.1rem .4rem', borderRadius: 999,
                              background: DEDUPE_BADGE[item.dedupe_status].bg,
                              color: DEDUPE_BADGE[item.dedupe_status].fg,
                            }}>
                              {DEDUPE_BADGE[item.dedupe_status].text}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {!imported && (
                <div style={{ display: 'flex', gap: '.5rem', marginTop: '1rem' }}>
                  <button className="btn btn-primary" onClick={handleImport} disabled={!canImport || importing}>
                    <Check size={16} /> {importing ? 'Importing…' : `Import ${selected.size} selected`}
                  </button>
                  <button className="btn btn-secondary" onClick={handleDiscard} disabled={importing}>
                    <X size={16} /> {t('PdfTools.discard')}
                  </button>
                </div>
              )}

              {!result.target_table && (
                <p style={{ fontSize: '.78rem', color: 'var(--color-text-tertiary)', marginTop: '.6rem' }}>
                  {t('PdfTools.this_document_type_can_be_read_but_not')}
                </p>
              )}
            </>
          )}

          {result.raw_text_preview && (
            <div style={{ marginTop: '1rem' }}>
              <button className="btn btn-secondary btn-sm" onClick={() => setShowRaw(!showRaw)}>
                <FileText size={14} /> {(showRaw) ? t('PdfTools.hide_extracted_text') : t('PdfTools.show_extracted_text')}
              </button>
              {showRaw && <pre style={preStyle}>{result.raw_text_preview}</pre>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function GenerateFlowsheet() {
  const [form, setForm] = useState({ session_type: 'hemodialysis', days: 30 });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.post('/pdf/generate-flowsheet', {
        session_type: form.session_type,
        days: parseInt(form.days, 10),
      });
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(err?.response?.data?.detail || 'The flowsheet could not be generated.');
    } finally {
      setLoading(false);
    }
  }

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      // Goes through the api client so the auth header is attached; a plain
      // link would hit the endpoint unauthenticated.
      const response = await api.get('/pdf/reports/flowsheet.pdf', {
        params: { session_type: form.session_type, days: parseInt(form.days, 10) },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `flowsheet_${form.session_type}_${new Date().toISOString().slice(0, 10)}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t('PdfTools.the_pdf_could_not_be_downloaded'));
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <h3 style={{ marginBottom: '1rem' }}>{t('PdfTools.generate_dialysis_flowsheet')}</h3>
      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="form-group">
            <label className="form-label">{t('PdfTools.session_type')}</label>
            <select className="form-select" value={form.session_type}
              onChange={e => setForm(p => ({ ...p, session_type: e.target.value }))}>
              <option value="hemodialysis">{t('PdfTools.hemodialysis')}</option>
              <option value="peritoneal_dialysis">{t('PdfTools.peritoneal_dialysis')}</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">{t('PdfTools.days')}</label>
            <input type="number" className="form-input" min={1} max={365} value={form.days}
              onChange={e => setForm(p => ({ ...p, days: e.target.value }))} />
          </div>
        </div>
        <button className="btn btn-primary" disabled={loading}>
          <FileBarChart size={16} /> {(loading) ? t('PdfTools.generating') : t('PdfTools.generate')}
        </button>
      </form>

      {error && (
        <div style={bannerStyle('#fee2e2', '#fca5a5', '#b91c1c')}>
          <AlertTriangle size={15} /> {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '.75rem' }}>
            <div>
              <h4 style={{ margin: 0 }}>{result.title}</h4>
              <p style={{ fontSize: '.85rem', color: 'var(--color-text-secondary)', margin: 0 }}>
                {(result.session_count === 1) ? t('PdfTools.session_generated', { session_count: result.session_count, generated_at: result.generated_at }) : t('PdfTools.sessions_generated', { session_count: result.session_count, generated_at: result.generated_at })}
              </p>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={handleDownload} disabled={downloading}>
              <Download size={14} /> {(downloading) ? t('PdfTools.preparing') : t('PdfTools.download_pdf')}
            </button>
          </div>
          <pre style={preStyle}>{result.content}</pre>
        </div>
      )}
    </div>
  );
}

const thStyle = { textAlign: 'left', padding: '0.5rem', fontSize: '0.78rem', color: 'var(--color-text-secondary)' };
const tdStyle = { padding: '0.5rem', verticalAlign: 'top' };
const preStyle = {
  marginTop: '0.5rem', padding: '1rem', background: 'var(--color-bg)', borderRadius: 8,
  fontSize: '0.78rem', maxHeight: 500, overflow: 'auto', whiteSpace: 'pre-wrap',
  fontFamily: 'monospace', lineHeight: 1.4,
};

function bannerStyle(bg, border, fg) {
  return {
    display: 'flex', alignItems: 'center', gap: '.4rem',
    marginTop: '1rem', padding: '.6rem .75rem', borderRadius: 8,
    background: bg, border: `1px solid ${border}`, color: fg, fontSize: '.83rem',
  };
}
