import { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus } from 'lucide-react';
import BackButton from '../components/BackButton';

export default function Medications() {
  const [meds, setMeds] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: '',
    dosage: '',
    dosage_unit: '',
    frequency: '',
    route: 'oral',
    start_date: new Date().toISOString().split('T')[0],
    end_date: '',
    prescribing_doctor: '',
    reason: '',
    is_active: true,
  });

  useEffect(() => { loadMeds(); }, []);

  async function loadMeds() {
    const { data } = await api.get('/medications/');
    setMeds(data);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    await api.post('/medications/', form);
    setShowForm(false);
    loadMeds();
  }

  async function handleDelete(id) {
    await api.delete(`/medications/${id}`);
    loadMeds();
  }

  async function toggleActive(med) {
    await api.patch(`/medications/${med.id}`, { is_active: !med.is_active });
    loadMeds();
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Medications</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={18} /> Add Medication
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Medication Name</label>
                <input className="form-input" value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">Dosage</label>
                <input className="form-input" value={form.dosage}
                  onChange={(e) => setForm({ ...form, dosage: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Unit</label>
                <input className="form-input" value={form.dosage_unit} placeholder="mg, ml, etc."
                  onChange={(e) => setForm({ ...form, dosage_unit: e.target.value })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Frequency</label>
                <input className="form-input" value={form.frequency} placeholder="e.g., twice daily"
                  onChange={(e) => setForm({ ...form, frequency: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Route</label>
                <select className="form-input" value={form.route}
                  onChange={(e) => setForm({ ...form, route: e.target.value })}>
                  <option value="oral">Oral</option>
                  <option value="topical">Topical</option>
                  <option value="injection">Injection</option>
                  <option value="inhalation">Inhalation</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Start Date</label>
                <input className="form-input" type="date" value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">End Date</label>
                <input className="form-input" type="date" value={form.end_date}
                  onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Prescribing Doctor</label>
                <input className="form-input" value={form.prescribing_doctor}
                  onChange={(e) => setForm({ ...form, prescribing_doctor: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Reason</label>
                <input className="form-input" value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })} />
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
              <th>Name</th>
              <th>Dosage</th>
              <th>Frequency</th>
              <th>Route</th>
              <th>Start Date</th>
              <th>End Date</th>
              <th>Date Logged</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {meds.map((med) => (
              <tr key={med.id}>
                <td>{med.name}</td>
                <td>{med.dosage} {med.dosage_unit}</td>
                <td>{med.frequency ?? '-'}</td>
                <td>{med.route ?? '-'}</td>
                <td>{med.start_date ?? '-'}</td>
                <td>{med.end_date ?? '-'}</td>
                <td>{med.created_at ? new Date(med.created_at).toLocaleDateString() : '-'}</td>
                <td>
                  <button
                    className={`btn btn-sm ${med.is_active ? 'btn-success' : 'btn-secondary'}`}
                    style={{ minWidth: 90 }}
                    onClick={() => toggleActive(med)}
                    title="Click to toggle active status"
                  >
                    {med.is_active ? '🟢 Active' : '⚪ Inactive'}
                  </button>
                </td>
                <td>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(med.id)}>Delete</button>
                </td>
              </tr>
            ))}
            {meds.length === 0 && (
              <tr><td colSpan={9} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>No medications yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
