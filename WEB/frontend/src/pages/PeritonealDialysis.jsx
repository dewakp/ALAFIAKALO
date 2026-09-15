import { localToday } from '../utils/datetime';
import { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus, Trash2, Droplets, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import BackButton from '../components/BackButton';
import { t } from '../i18n';

export default function PeritonealDialysis() {
  const [sessions, setSessions] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [form, setForm] = useState({
    condition_id: '',
    session_date: localToday(),
    modality: 'capd',
    pre_weight_kg: '',
    post_weight_kg: '',
    pre_bp_systolic: '',
    pre_bp_diastolic: '',
    post_bp_systolic: '',
    post_bp_diastolic: '',
    temperature_c: '',
    exit_site_status: 'healthy',
    machine_type: '',
    total_volume_ml: '',
    fill_volume_ml: '',
    cycles: '',
    therapy_time_minutes: '',
    last_fill_ml: '',
    complications: '',
    notes: '',
    exchanges: [],
  });

  useEffect(() => { loadSessions(); }, []);

  async function loadSessions() {
    try {
      const { data } = await api.get('/pd/sessions');
      setSessions(data);
    } catch (err) {
      console.error(err);
    }
  }

  function addExchange() {
    setForm(p => ({
      ...p,
      exchanges: [...p.exchanges, {
        exchange_number: p.exchanges.length + 1,
        start_time: '',
        drain_start_time: '',
        drain_end_time: '',
        fill_end_time: '',
        solution_type: '1.5% Dextrose',
        inflow_volume_ml: '',
        outflow_volume_ml: '',
        effluent_clarity: 'clear',
        effluent_color: '',
      }],
    }));
  }

  function removeExchange(idx) {
    setForm(p => ({
      ...p,
      exchanges: p.exchanges.filter((_, i) => i !== idx).map((ex, i) => ({ ...ex, exchange_number: i + 1 })),
    }));
  }

  function updateExchange(idx, field, value) {
    setForm(p => ({
      ...p,
      exchanges: p.exchanges.map((ex, i) => i === idx ? { ...ex, [field]: value } : ex),
    }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const payload = { ...form };
    // Parse numbers
    ['pre_weight_kg', 'post_weight_kg', 'temperature_c'].forEach(k => {
      payload[k] = payload[k] ? parseFloat(payload[k]) : null;
    });
    ['pre_bp_systolic', 'pre_bp_diastolic', 'post_bp_systolic', 'post_bp_diastolic',
     'total_volume_ml', 'fill_volume_ml', 'cycles', 'therapy_time_minutes', 'last_fill_ml', 'condition_id'].forEach(k => {
      payload[k] = payload[k] ? parseInt(payload[k]) : null;
    });
    payload.exchanges = payload.exchanges.map(ex => ({
      ...ex,
      inflow_volume_ml: ex.inflow_volume_ml ? parseInt(ex.inflow_volume_ml) : null,
      outflow_volume_ml: ex.outflow_volume_ml ? parseInt(ex.outflow_volume_ml) : null,
    }));
    try {
      await api.post('/pd/sessions', payload);
      setShowForm(false);
      loadSessions();
    } catch (err) {
      alert(t('PeritonealDialysis.error_creating_session'));
    }
  }

  async function handleDelete(id) {
    if (!confirm(t('PeritonealDialysis.delete_this_pd_session'))) return;
    await api.delete(`/pd/sessions/${id}`);
    loadSessions();
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">{t('PeritonealDialysis.peritoneal_dialysis')}</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={16} /> {t('PeritonealDialysis.new_session')}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>{t('PeritonealDialysis.new_pd_session')}</h3>
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">{t('PeritonealDialysis.date')}</label>
                <input type="date" className="form-input" value={form.session_date}
                  onChange={e => setForm(p => ({ ...p, session_date: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label className="form-label">{t('PeritonealDialysis.modality')}</label>
                <select className="form-select" value={form.modality}
                  onChange={e => setForm(p => ({ ...p, modality: e.target.value }))}>
                  <option value="capd">CAPD</option>
                  <option value="apd">APD</option>
                  <option value="ccpd">CCPD</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{t('PeritonealDialysis.exit_site_status')}</label>
                <select className="form-select" value={form.exit_site_status}
                  onChange={e => setForm(p => ({ ...p, exit_site_status: e.target.value }))}>
                  <option value="healthy">{t('PeritonealDialysis.healthy')}</option>
                  <option value="redness">{t('PeritonealDialysis.redness')}</option>
                  <option value="drainage">{t('PeritonealDialysis.drainage')}</option>
                  <option value="crusting">{t('PeritonealDialysis.crusting')}</option>
                  <option value="pain">{t('PeritonealDialysis.pain')}</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{t('PeritonealDialysis.pre_weight_kg')}</label>
                <input type="number" step="0.1" className="form-input" value={form.pre_weight_kg}
                  onChange={e => setForm(p => ({ ...p, pre_weight_kg: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('PeritonealDialysis.post_weight_kg')}</label>
                <input type="number" step="0.1" className="form-input" value={form.post_weight_kg}
                  onChange={e => setForm(p => ({ ...p, post_weight_kg: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('PeritonealDialysis.temperature_c')}</label>
                <input type="number" step="0.1" className="form-input" value={form.temperature_c}
                  onChange={e => setForm(p => ({ ...p, temperature_c: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('PeritonealDialysis.pre_bp_sys_dia')}</label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <input type="number" className="form-input" placeholder={t('PeritonealDialysis.sys')} value={form.pre_bp_systolic}
                    onChange={e => setForm(p => ({ ...p, pre_bp_systolic: e.target.value }))} />
                  <input type="number" className="form-input" placeholder={t('PeritonealDialysis.dia')} value={form.pre_bp_diastolic}
                    onChange={e => setForm(p => ({ ...p, pre_bp_diastolic: e.target.value }))} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">{t('PeritonealDialysis.post_bp_sys_dia')}</label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <input type="number" className="form-input" placeholder={t('PeritonealDialysis.sys')} value={form.post_bp_systolic}
                    onChange={e => setForm(p => ({ ...p, post_bp_systolic: e.target.value }))} />
                  <input type="number" className="form-input" placeholder={t('PeritonealDialysis.dia')} value={form.post_bp_diastolic}
                    onChange={e => setForm(p => ({ ...p, post_bp_diastolic: e.target.value }))} />
                </div>
              </div>
            </div>

            {form.modality !== 'capd' && (
              <div style={{ marginTop: '1rem' }}>
                <h4 style={{ marginBottom: '0.5rem' }}>{t('PeritonealDialysis.apd_machine_settings')}</h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                  <div className="form-group">
                    <label className="form-label">{t('PeritonealDialysis.machine_type')}</label>
                    <input className="form-input" value={form.machine_type}
                      onChange={e => setForm(p => ({ ...p, machine_type: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{t('PeritonealDialysis.total_volume_ml')}</label>
                    <input type="number" className="form-input" value={form.total_volume_ml}
                      onChange={e => setForm(p => ({ ...p, total_volume_ml: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{t('PeritonealDialysis.fill_volume_ml')}</label>
                    <input type="number" className="form-input" value={form.fill_volume_ml}
                      onChange={e => setForm(p => ({ ...p, fill_volume_ml: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{t('PeritonealDialysis.cycles')}</label>
                    <input type="number" className="form-input" value={form.cycles}
                      onChange={e => setForm(p => ({ ...p, cycles: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{t('PeritonealDialysis.therapy_time_min')}</label>
                    <input type="number" className="form-input" value={form.therapy_time_minutes}
                      onChange={e => setForm(p => ({ ...p, therapy_time_minutes: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{t('PeritonealDialysis.last_fill_ml')}</label>
                    <input type="number" className="form-input" value={form.last_fill_ml}
                      onChange={e => setForm(p => ({ ...p, last_fill_ml: e.target.value }))} />
                  </div>
                </div>
              </div>
            )}

            <div style={{ marginTop: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <h4>{t('PeritonealDialysis.exchanges', { exchanges: form.exchanges.length })}</h4>
                <button type="button" className="btn btn-secondary btn-sm" onClick={addExchange}>
                  <Plus size={14} /> {t('PeritonealDialysis.add_exchange')}
                </button>
              </div>
              {form.exchanges.map((ex, i) => (
                <div key={i} className="card" style={{ padding: '1rem', marginBottom: '0.75rem', background: 'var(--color-bg)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <strong>{t('PeritonealDialysis.exchange', { exchange_number: ex.exchange_number })}</strong>
                    <button type="button" className="btn btn-sm" style={{ color: 'var(--color-danger)' }} onClick={() => removeExchange(i)}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
                    <div className="form-group">
                      <label className="form-label">{t('PeritonealDialysis.solution_type')}</label>
                      <select className="form-select" value={ex.solution_type}
                        onChange={e => updateExchange(i, 'solution_type', e.target.value)}>
                        <option>{t('PeritonealDialysis.text_1_5_dextrose')}</option>
                        <option>{t('PeritonealDialysis.text_2_5_dextrose')}</option>
                        <option>{t('PeritonealDialysis.text_4_25_dextrose')}</option>
                        <option>{t('PeritonealDialysis.icodextrin')}</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('PeritonealDialysis.inflow_ml')}</label>
                      <input type="number" className="form-input" value={ex.inflow_volume_ml}
                        onChange={e => updateExchange(i, 'inflow_volume_ml', e.target.value)} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('PeritonealDialysis.outflow_ml')}</label>
                      <input type="number" className="form-input" value={ex.outflow_volume_ml}
                        onChange={e => updateExchange(i, 'outflow_volume_ml', e.target.value)} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('PeritonealDialysis.effluent_clarity')}</label>
                      <select className="form-select" value={ex.effluent_clarity}
                        onChange={e => updateExchange(i, 'effluent_clarity', e.target.value)}>
                        <option value="clear">{t('PeritonealDialysis.clear')}</option>
                        <option value="slightly_cloudy">{t('PeritonealDialysis.slightly_cloudy')}</option>
                        <option value="cloudy">{t('PeritonealDialysis.cloudy')}</option>
                        <option value="bloody">{t('PeritonealDialysis.bloody')}</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('PeritonealDialysis.start_time')}</label>
                      <input type="time" className="form-input" value={ex.start_time}
                        onChange={e => updateExchange(i, 'start_time', e.target.value)} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('PeritonealDialysis.drain_start')}</label>
                      <input type="time" className="form-input" value={ex.drain_start_time}
                        onChange={e => updateExchange(i, 'drain_start_time', e.target.value)} />
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="form-group" style={{ marginTop: '1rem' }}>
              <label className="form-label">{t('PeritonealDialysis.notes')}</label>
              <textarea className="form-input" rows={2} value={form.notes}
                onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} />
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem' }}>
              <button type="submit" className="btn btn-primary">{t('PeritonealDialysis.save_session')}</button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>{t('PeritonealDialysis.cancel')}</button>
            </div>
          </form>
        </div>
      )}

      {sessions.length === 0 ? (
        <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
          {t('PeritonealDialysis.no_pd_sessions_recorded_yet')}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {sessions.map(s => (
            <div key={s.id} className="card" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                onClick={() => setExpanded(expanded === s.id ? null : s.id)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <Droplets size={20} color="var(--color-info)" />
                  <div>
                    <strong>{s.session_date}</strong>
                    <span style={{
                      marginLeft: '0.75rem', padding: '2px 8px', borderRadius: 10,
                      fontSize: '0.75rem', fontWeight: 600, background: 'var(--color-primary-light)',
                      color: 'var(--color-primary-dark)', textTransform: 'uppercase',
                    }}>{s.modality}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  {s.total_uf_ml != null && <span style={{ fontSize: '0.85rem' }}>{t('PeritonealDialysis.uf_ml', { total_uf_ml: s.total_uf_ml })}</span>}
                  {expanded === s.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </div>
              </div>

              {expanded === s.id && (
                <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem', fontSize: '0.9rem' }}>
                    {s.pre_weight_kg && <div><strong>{t('PeritonealDialysis.pre_weight')}</strong> {t('PeritonealDialysis.kg', { pre_weight_kg: s.pre_weight_kg })}</div>}
                    {s.post_weight_kg && <div><strong>{t('PeritonealDialysis.post_weight')}</strong> {t('PeritonealDialysis.kg_2', { post_weight_kg: s.post_weight_kg })}</div>}
                    {s.pre_bp_systolic && <div><strong>{t('PeritonealDialysis.pre_bp')}</strong> {s.pre_bp_systolic}/{s.pre_bp_diastolic}</div>}
                    {s.post_bp_systolic && <div><strong>{t('PeritonealDialysis.post_bp')}</strong> {s.post_bp_systolic}/{s.post_bp_diastolic}</div>}
                    {s.temperature_c && <div><strong>{t('PeritonealDialysis.temp')}</strong> {s.temperature_c}°C</div>}
                    {s.exit_site_status && <div><strong>{t('PeritonealDialysis.exit_site')}</strong> {s.exit_site_status}</div>}
                  </div>
                  {s.exchanges?.length > 0 && (
                    <div style={{ marginTop: '0.75rem' }}>
                      <strong>{t('PeritonealDialysis.exchanges', { exchanges: s.exchanges.length })}</strong>
                      <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '0.5rem', fontSize: '0.85rem' }}>
                        <thead>
                          <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                            <th style={thStyle}>#</th>
                            <th style={thStyle}>{t('PeritonealDialysis.solution')}</th>
                            <th style={thStyle}>{t('PeritonealDialysis.in_ml')}</th>
                            <th style={thStyle}>{t('PeritonealDialysis.out_ml')}</th>
                            <th style={thStyle}>{t('PeritonealDialysis.uf_ml_2')}</th>
                            <th style={thStyle}>{t('PeritonealDialysis.clarity')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {s.exchanges.map(ex => (
                            <tr key={ex.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                              <td style={tdStyle}>{ex.exchange_number}</td>
                              <td style={tdStyle}>{ex.solution_type}</td>
                              <td style={tdStyle}>{ex.inflow_volume_ml}</td>
                              <td style={tdStyle}>{ex.outflow_volume_ml}</td>
                              <td style={tdStyle}>{ex.uf_ml}</td>
                              <td style={tdStyle}>{ex.effluent_clarity}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem' }}>
                    <button className="btn btn-sm" style={{ color: 'var(--color-danger)' }} onClick={() => handleDelete(s.id)}>
                      <Trash2 size={14} /> {t('PeritonealDialysis.delete')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const thStyle = { textAlign: 'left', padding: '0.4rem 0.5rem', color: 'var(--color-text-secondary)' };
const tdStyle = { padding: '0.4rem 0.5rem' };
