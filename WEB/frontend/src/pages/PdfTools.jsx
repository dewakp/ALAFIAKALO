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

const DOC_TYPE_LABEL = {
  lab_report: 'Lab report',
  medication_list: 'Medication list',
  discharge_summary: 'Discharge summary',
  dialysis_flowsheet: 'Dialysis flowsheet',
  imaging_report: 'Imaging report',
  unknown: 'Unrecognised document',
};

function ImportDocument() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [imported, setImported] = useState(null);
  const [error, setError] = useState(null);
  const [showRaw, setShowRaw] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    setError(null);
    setImported(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post('/pdf/parse-document', fd);
      setResult(data);
      // Pre-tick what the server judged safe to import — duplicates stay off.
      setSelected(new Set(data.items.filter(i => i.accepted).map(i => i.item_id)));
    } catch (err) {
      setResult(null);
      setError(err?.response?.data?.detail || 'The document could not be read.');
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
    if (!result?.import_id) return;
    setImporting(true);
    setError(null);
    try {
      const { data } = await api.post(`/pdf/imports/${result.import_id}/confirm`, {
        accepted_item_ids: [...selected],
      });
      setImported(data);
    } catch (err) {
      setError(err?.response?.data?.detail || 'The import could not be completed.');
    } finally {
      setImporting(false);
    }
  }

  async function handleDiscard() {
    if (!result?.import_id) return;
    try { await api.post(`/pdf/imports/${result.import_id}/reject`); } catch { /* already gone */ }
    setResult(null); setSelected(new Set()); setImported(null); setFile(null);
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
          <input type="file" accept=".pdf,.txt" className="form-input"
            onChange={e => { setFile(e.target.files[0]); setResult(null); setImported(null); setError(null); }} />
        </div>
        <button className="btn btn-primary" disabled={!file || loading}>
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

      {imported && (
        <div style={bannerStyle('#dcfce7', '#86efac', '#15803d')}>
          <Check size={15} /> {imported.message}
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
