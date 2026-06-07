import { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus } from 'lucide-react';
import BackButton from '../components/BackButton';

export default function Labs() {
  const [results, setResults] = useState([]);
  const [providers, setProviders] = useState([]);
  const [connections, setConnections] = useState([]);
  const [connectForm, setConnectForm] = useState({
    provider: '',
    fhir_base_url: '',
    patient_id: '',
    scopes: '',
    notes: '',
  });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    test_date: new Date().toISOString().split('T')[0],
    test_name: '',
    loinc_code: '',
    category: '',
    value: '',
    unit: '',
    reference_range_low: '',
    reference_range_high: '',
    is_abnormal: false,
    performing_lab: '',
    notes: '',
  });

  useEffect(() => {
    loadResults();
    loadProviders();
    loadConnections();
  }, []);

  async function loadResults() {
    const { data } = await api.get('/labs/');
    setResults(data);
  }

  async function loadProviders() {
    const { data } = await api.get('/ehr/providers');
    setProviders(data);
    if (!connectForm.provider && data.length > 0) {
      setConnectForm((prev) => ({ ...prev, provider: data[0].name }));
    }
  }

  async function loadConnections() {
    const { data } = await api.get('/ehr/connections');
    setConnections(data);
  }

  async function handleConnect(e) {
    e.preventDefault();
    await api.post('/ehr/connections', connectForm);
    setConnectForm({ provider: '', fhir_base_url: '', patient_id: '', scopes: '', notes: '' });
    loadConnections();
  }

  async function handleDisconnect(id) {
    await api.delete(`/ehr/connections/${id}`);
    loadConnections();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const payload = { ...form };
    ['value', 'reference_range_low', 'reference_range_high'].forEach((k) => {
      payload[k] = payload[k] ? parseFloat(payload[k]) : null;
    });
    await api.post('/labs/', payload);
    setShowForm(false);
    loadResults();
  }

  async function handleDelete(id) {
    await api.delete(`/labs/${id}`);
    loadResults();
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Labs / EHR</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={18} /> Add Result
        </button>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">
          <span className="card-title">EHR Connections (FHIR)</span>
        </div>
        <form onSubmit={handleConnect}>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Provider</label>
              <select
                className="form-input"
                value={connectForm.provider}
                onChange={(e) => setConnectForm({ ...connectForm, provider: e.target.value })}
              >
                {providers.map((p) => (
                  <option key={p.id} value={p.name}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">FHIR Base URL</label>
              <input
                className="form-input"
                value={connectForm.fhir_base_url}
                onChange={(e) => setConnectForm({ ...connectForm, fhir_base_url: e.target.value })}
                placeholder="https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Patient ID</label>
              <input
                className="form-input"
                value={connectForm.patient_id}
                onChange={(e) => setConnectForm({ ...connectForm, patient_id: e.target.value })}
              />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Scopes</label>
              <input
                className="form-input"
                value={connectForm.scopes}
                onChange={(e) => setConnectForm({ ...connectForm, scopes: e.target.value })}
                placeholder="patient/Observation.read patient/Condition.read"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <input
                className="form-input"
                value={connectForm.notes}
                onChange={(e) => setConnectForm({ ...connectForm, notes: e.target.value })}
              />
            </div>
          </div>
          <button className="btn btn-primary" type="submit">Add Connection</button>
        </form>

        <div style={{ marginTop: '1rem' }}>
          {connections.length === 0 && (
            <div style={{ color: 'var(--color-text-secondary)' }}>No EHR connections yet.</div>
          )}
          {connections.map((conn) => (
            <div key={conn.id} className="card" style={{ marginTop: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{conn.provider}</div>
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
                    Status: {conn.status}
                  </div>
                  {conn.fhir_base_url && (
                    <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.85rem' }}>
                      {conn.fhir_base_url}
                    </div>
                  )}
                </div>
                <button className="btn btn-danger btn-sm" onClick={() => handleDisconnect(conn.id)}>
                  Disconnect
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Date</label>
                <input className="form-input" type="date" value={form.test_date}
                  onChange={(e) => setForm({ ...form, test_date: e.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">Test Name</label>
                <input className="form-input" value={form.test_name}
                  onChange={(e) => setForm({ ...form, test_name: e.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">LOINC Code</label>
                <input className="form-input" value={form.loinc_code}
                  onChange={(e) => setForm({ ...form, loinc_code: e.target.value })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Value</label>
                <input className="form-input" type="number" step="any" value={form.value}
                  onChange={(e) => setForm({ ...form, value: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Unit</label>
                <input className="form-input" value={form.unit}
                  onChange={(e) => setForm({ ...form, unit: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Reference Low</label>
                <input className="form-input" type="number" step="any" value={form.reference_range_low}
                  onChange={(e) => setForm({ ...form, reference_range_low: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Reference High</label>
                <input className="form-input" type="number" step="any" value={form.reference_range_high}
                  onChange={(e) => setForm({ ...form, reference_range_high: e.target.value })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Category</label>
                <input className="form-input" value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Performing Lab</label>
                <input className="form-input" value={form.performing_lab}
                  onChange={(e) => setForm({ ...form, performing_lab: e.target.value })} />
              </div>
            </div>
            <button className="btn btn-primary" type="submit">Save</button>
          </form>
        </div>
      )}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Test</th>
              <th>Value</th>
              <th>Unit</th>
              <th>Range</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.id} style={r.is_abnormal ? { background: '#fef2f2' } : {}}>
                <td>{r.test_date}</td>
                <td>{r.test_name}</td>
                <td>{r.value ?? r.value_string ?? '-'}</td>
                <td>{r.unit ?? '-'}</td>
                <td>{r.reference_range_low != null ? `${r.reference_range_low} - ${r.reference_range_high}` : '-'}</td>
                <td>{r.is_abnormal ? '⚠️ Abnormal' : '✅ Normal'}</td>
                <td>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(r.id)}>Delete</button>
                </td>
              </tr>
            ))}
            {results.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>No lab results yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
