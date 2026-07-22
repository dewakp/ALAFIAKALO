import { localToday } from '../utils/datetime';
import { useState } from 'react';
import api from '../services/api';
import { FileText, Download, Upload, FileBarChart } from 'lucide-react';
import BackButton from '../components/BackButton';

const tabs = [
  { key: 'parse', label: 'Parse Lab Report', icon: Upload },
  { key: 'flowsheet', label: 'Generate Flowsheet', icon: FileBarChart },
];

export default function PdfTools() {
  const [activeTab, setActiveTab] = useState('parse');

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">PDF Tools</h1>
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
      {activeTab === 'parse' && <ParseLabReport />}
      {activeTab === 'flowsheet' && <GenerateFlowsheet />}
    </div>
  );
}

function ParseLabReport() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post('/pdf/parse-lab-report', fd);
      setResult(data);
    } catch (err) {
      alert('Error parsing report');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <h3 style={{ marginBottom: '1rem' }}>Parse Lab Report</h3>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">Upload Lab Report (PDF or TXT)</label>
          <input type="file" accept=".pdf,.txt" onChange={e => { setFile(e.target.files[0]); setResult(null); }} className="form-input" />
        </div>
        <button className="btn btn-primary" disabled={!file || loading}>
          <Upload size={16} /> {loading ? 'Parsing...' : 'Parse Report'}
        </button>
      </form>

      {result && (
        <div style={{ marginTop: '1.5rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
            {result.patient_name && <div><strong>Patient:</strong> {result.patient_name}</div>}
            {result.report_date && <div><strong>Date:</strong> {result.report_date}</div>}
            {result.lab_name && <div><strong>Lab:</strong> {result.lab_name}</div>}
            {result.ordering_physician && <div><strong>Physician:</strong> {result.ordering_physician}</div>}
          </div>

          {result.items?.length > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                  <th style={thStyle}>Test</th>
                  <th style={thStyle}>Value</th>
                  <th style={thStyle}>Unit</th>
                  <th style={thStyle}>Reference</th>
                  <th style={thStyle}>Status</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((item, i) => (
                  <tr key={i} style={{
                    borderBottom: '1px solid var(--color-border)',
                    background: item.is_abnormal ? '#fee2e2' : 'transparent',
                  }}>
                    <td style={tdStyle}>{item.test_name}</td>
                    <td style={tdStyle}><strong>{item.value}</strong></td>
                    <td style={tdStyle}>{item.unit}</td>
                    <td style={tdStyle}>{item.reference_range || '—'}</td>
                    <td style={tdStyle}>
                      {item.is_abnormal ? (
                        <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>Abnormal</span>
                      ) : (
                        <span style={{ color: 'var(--color-primary)' }}>Normal</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {result.raw_text_preview && (
            <div style={{ marginTop: '1rem' }}>
              <button className="btn btn-secondary btn-sm" onClick={() => setShowRaw(!showRaw)}>
                <FileText size={14} /> {showRaw ? 'Hide' : 'Show'} Raw Text
              </button>
              {showRaw && (
                <pre style={{
                  marginTop: '0.5rem', padding: '1rem', background: 'var(--color-bg)',
                  borderRadius: 8, fontSize: '0.8rem', maxHeight: 300, overflow: 'auto',
                  whiteSpace: 'pre-wrap', wordWrap: 'break-word',
                }}>
                  {result.raw_text_preview}
                </pre>
              )}
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

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post('/pdf/generate-flowsheet', {
        session_type: form.session_type,
        days: parseInt(form.days),
      });
      setResult(data);
    } catch (err) {
      alert('Error generating flowsheet');
    } finally {
      setLoading(false);
    }
  }

  function handleDownload() {
    if (!result) return;
    const blob = new Blob([result.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `flowsheet_${form.session_type}_${localToday()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <h3 style={{ marginBottom: '1rem' }}>Generate Dialysis Flowsheet</h3>
      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="form-group">
            <label className="form-label">Session Type</label>
            <select className="form-select" value={form.session_type}
              onChange={e => setForm(p => ({ ...p, session_type: e.target.value }))}>
              <option value="hemodialysis">Hemodialysis</option>
              <option value="peritoneal_dialysis">Peritoneal Dialysis</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Days</label>
            <input type="number" className="form-input" min={1} max={365} value={form.days}
              onChange={e => setForm(p => ({ ...p, days: e.target.value }))} />
          </div>
        </div>
        <button className="btn btn-primary" disabled={loading}>
          <FileBarChart size={16} /> {loading ? 'Generating...' : 'Generate'}
        </button>
      </form>

      {result && (
        <div style={{ marginTop: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <div>
              <h4>{result.title}</h4>
              <p style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
                {result.session_count} sessions · Generated {result.generated_at}
              </p>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={handleDownload}>
              <Download size={14} /> Download
            </button>
          </div>
          <pre style={{
            padding: '1rem', background: 'var(--color-bg)', borderRadius: 8,
            fontSize: '0.8rem', maxHeight: 500, overflow: 'auto', whiteSpace: 'pre-wrap',
            fontFamily: 'monospace', lineHeight: 1.4,
          }}>
            {result.content}
          </pre>
        </div>
      )}
    </div>
  );
}

const thStyle = { textAlign: 'left', padding: '0.5rem', fontSize: '0.85rem', color: 'var(--color-text-secondary)' };
const tdStyle = { padding: '0.5rem' };
