import { localToday } from '../utils/datetime';
import { detachFile } from '../utils/fileInput';
import { useState, useEffect, useCallback, useMemo } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Plus, Trash2, Pill, ChevronLeft, ChevronRight, Camera, Loader2 } from 'lucide-react';
import BackButton from '../components/BackButton';
import { usePromptPrefill } from '../hooks/usePromptPrefill';
import { useTempUnit } from '../hooks/useTempUnit';

// Combined medication view (ALAFIA.app reference): a "Log New Medication Intake"
// form with the history calendar beside it, and date-filtered intake cards.
// The legacy ai_analysis error blob in synced notes is stripped from display.

const todayStr = () => localToday();
const nowTime = () => new Date().toTimeString().slice(0, 5);
const fmtLong = (d) => new Date(d + 'T12:00:00').toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
const numOrNull = (v) => (v !== '' && v != null ? Number(v) : null);

// Legacy synced notes packed structured tokens + a Gemini error JSON; hide those.
function cleanNotes(notes) {
  if (!notes) return '';
  return notes.split(' | ')
    .filter((p) => !/^(ai_analysis=|time=|pre_BP=|pre_HR=|post_BP=|post_HR=)/.test(p.trim()))
    .join(' | ')
    .trim();
}
function timeFromNotes(notes) {
  const m = (notes || '').match(/time=(\d{1,2}:\d{2})/);
  return m ? m[1] : '';
}
function parseDosage(s) {
  const m = String(s || '').trim().match(/^([\d.]+)\s*(.*)$/);
  if (m) return { dose_amount: parseFloat(m[1]) || 1, dose_unit: (m[2] || 'dose').trim() };
  return { dose_amount: 1, dose_unit: String(s || '').trim() || 'dose' };
}

const EMPTY_LOG = {
  log_date: todayStr(), log_time: nowTime(), medication_name: '', dosage: '',
  pre_systolic_bp: '', pre_diastolic_bp: '', pre_heart_rate: '', pre_temp: '',
  post_systolic_bp: '', post_diastolic_bp: '', post_heart_rate: '', post_temp: '',
  notes: '',
};

const EMPTY_RX = {
  name: '', dosage: '', dosage_unit: '', frequency: '', route: 'oral',
  start_date: todayStr(), end_date: '', prescribing_doctor: '', reason: '', is_active: true,
};

export default function Medications() {
  const [meds, setMeds] = useState([]);          // prescription catalog
  const [doseLogs, setDoseLogs] = useState([]);  // intake events
  const [log, setLog] = useState({ ...EMPTY_LOG });
  const [savingLog, setSavingLog] = useState(false);
  const [selectedDate, setSelectedDate] = useState(todayStr());
  const [viewMonth, setViewMonth] = useState(() => { const d = new Date(); d.setDate(1); return d; });
  // Opens itself when there is nothing current to pick from: the section was
  // collapsed by default, so a user with no usable prescriptions saw no way to
  // enter one and reported that the app had no such feature at all.
  const [showRx, setShowRx] = useState(false);
  const [rx, setRx] = useState({ ...EMPTY_RX });
  const [intakeText, setIntakeText] = useState('');
  const [intakeBusy, setIntakeBusy] = useState(false);
  const [intakeError, setIntakeError] = useState(null);
  const [proposal, setProposal] = useState(null);
  const [scanning, setScanning] = useState(false);
  const temp = useTempUnit();

  /* Scan a bottle/label photo → AI reads the label → prefill the intake log
     and the prescription form. */
  async function scanLabel(e) {
    // Detach BEFORE clearing: the reset below strips the data off the
    // original File in WebKit, and FileReader would then read nothing.
    const file = await detachFile(e.target.files);
    e.target.value = '';
    if (!file) return;
    setScanning(true);
    try {
      const image_base64 = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.onerror = () => reject(new Error('Could not read the photo'));
        r.readAsDataURL(file);
      });
      const { data } = await api.post('/image-ai/medication-from-image',
        { image_base64 }, { timeout: 180000 });
      if (!data.medication_name || data.medication_name === 'Unknown Medication') {
        alert(data.instructions || 'Could not read the label — try a clearer photo.');
        return;
      }
      setLog((f) => ({
        ...f,
        medication_name: data.medication_name,
        dosage: data.dosage && data.dosage !== 'See label' ? data.dosage : f.dosage,
        notes: data.instructions ? `Label: ${data.instructions}` : f.notes,
      }));
      setRx((f) => ({
        ...f,
        name: data.medication_name,
        dosage: data.dosage && data.dosage !== 'See label' ? data.dosage : f.dosage,
      }));
    } catch (err) {
      alert(apiErrorMessage(err, 'Could not scan the label'));
    } finally { setScanning(false); }
  }

  function handleTempToggle() {
    setLog((f) => ({
      ...f,
      pre_temp: f.pre_temp ? temp.convertInPlace(f.pre_temp) : f.pre_temp,
      post_temp: f.post_temp ? temp.convertInPlace(f.post_temp) : f.post_temp,
    }));
    temp.toggle();
  }

  usePromptPrefill((prefill) => {
    setLog((f) => ({
      ...f,
      medication_name: prefill.name || prefill.medication || f.medication_name,
      dosage: prefill.dose || prefill.dosage || f.dosage,
      notes: prefill.name ? f.notes : (prefill.text || f.notes),
    }));
  });

  const activeMeds = meds.filter((m) => m.is_active);
  // Has prescriptions on file, but every one of them is stopped — the state this
  // account was actually in. Say so rather than showing an empty picker.
  const onlyStaleMeds = meds.length > 0 && activeMeds.length === 0;

  const loadMeds = useCallback(async () => {
    try { const { data } = await api.get('/medications/'); setMeds(data); } catch { setMeds([]); }
  }, []);
  const loadDoseLogs = useCallback(async () => {
    try { const { data } = await api.get('/medications/dose-logs'); setDoseLogs(data); } catch { setDoseLogs([]); }
  }, []);
  useEffect(() => { loadMeds(); loadDoseLogs(); }, [loadMeds, loadDoseLogs]);
  useEffect(() => { if (meds.length === 0 || onlyStaleMeds) setShowRx(true); },
    [meds.length, onlyStaleMeds]);

  function up(field, value) { setLog((f) => ({ ...f, [field]: value })); }

  /* ── "I take Calcitriol" → a proposal you confirm ────────────────────────
     The backend reads the medication out of the text and, when no dose is
     stated, supplies the one this user actually logs, with its provenance. It
     writes NOTHING: on this data 6 of 9 user/medication pairs use more than one
     dose over time, so a proposal is honest and an auto-write is not. */
  async function readIntake() {
    const text = intakeText.trim();
    if (!text) return;
    setIntakeBusy(true); setProposal(null); setIntakeError(null);
    try {
      const { data } = await api.post('/medications/intake-intent', { text });
      setProposal(data);
      if (!data.medication_name) setIntakeError(data.provenance || 'No medication recognised.');
    } catch (e) {
      setIntakeError(e?.response?.data?.detail || e?.message || 'Could not read that.');
    } finally { setIntakeBusy(false); }
  }

  /* Drop the proposal into the form the user already knows, rather than
     logging behind their back. One glance, one button. */
  function acceptProposal() {
    if (!proposal?.medication_name) return;
    const dose = proposal.dose_amount != null
      ? `${proposal.dose_amount}${proposal.dose_unit ? ' ' + proposal.dose_unit : ''}` : '';
    setLog((f) => ({ ...f, medication_name: proposal.medication_name, dosage: dose }));
    setProposal(null); setIntakeText('');
  }

  async function submitLog(e) {
    e.preventDefault();
    if (!log.medication_name.trim()) { alert('Medication name is required'); return; }
    setSavingLog(true);
    try {
      const { dose_amount, dose_unit } = parseDosage(log.dosage);
      await api.post('/medications/dose-logs', {
        medication_name: log.medication_name.trim(),
        log_date: log.log_date,
        log_time: log.log_time || null,
        dose_amount, dose_unit,
        pre_systolic_bp: numOrNull(log.pre_systolic_bp),
        pre_diastolic_bp: numOrNull(log.pre_diastolic_bp),
        pre_heart_rate: numOrNull(log.pre_heart_rate),
        post_systolic_bp: numOrNull(log.post_systolic_bp),
        post_diastolic_bp: numOrNull(log.post_diastolic_bp),
        post_heart_rate: numOrNull(log.post_heart_rate),
        pre_temperature_c: temp.toCelsius(log.pre_temp),
        post_temperature_c: temp.toCelsius(log.post_temp),
        notes: log.notes || null,
      });
      setLog({ ...EMPTY_LOG, log_date: log.log_date });
      setSelectedDate(log.log_date);
      loadDoseLogs();
    } catch (err) {
      alert(apiErrorMessage(err, 'Could not log medication'));
    } finally { setSavingLog(false); }
  }

  async function deleteDose(id) {
    if (!confirm('Delete this intake entry?')) return;
    try { await api.delete(`/medications/dose-logs/${id}`); loadDoseLogs(); }
    catch (err) { alert(apiErrorMessage(err, 'Could not delete')); }
  }

  async function saveRx(e) {
    e.preventDefault();
    // Drop blanks rather than posting "" for a date the user left empty. The
    // backend normalises these too (all three clients can send them), but there
    // is no reason to transmit a value that means nothing.
    const payload = Object.fromEntries(
      Object.entries(rx).filter(([, v]) => !(typeof v === 'string' && v.trim() === '')),
    );
    try { await api.post('/medications/', payload); setRx({ ...EMPTY_RX }); loadMeds(); }
    catch (err) { alert(apiErrorMessage(err, 'Could not save medication')); }
  }
  async function deleteRx(id) { await api.delete(`/medications/${id}`); loadMeds(); }

  const doseTime = (d) => (d.log_time ? String(d.log_time).slice(0, 5) : timeFromNotes(d.notes));

  const datesWithEntries = useMemo(() => new Set(doseLogs.map((d) => d.log_date)), [doseLogs]);
  const dayDoses = useMemo(
    () => doseLogs
      .filter((d) => d.log_date === selectedDate)
      .sort((a, b) => (doseTime(a) < doseTime(b) ? -1 : 1)),
    [doseLogs, selectedDate]);

  const cells = useMemo(() => {
    const y = viewMonth.getFullYear(), m = viewMonth.getMonth();
    const first = new Date(y, m, 1).getDay();
    const days = new Date(y, m + 1, 0).getDate();
    const out = [];
    for (let i = 0; i < first; i++) out.push(null);
    for (let d = 1; d <= days; d++) out.push({ d, ds: `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}` });
    return out;
  }, [viewMonth]);
  function shiftMonth(n) { setViewMonth((v) => new Date(v.getFullYear(), v.getMonth() + n, 1)); }
  const monthLabel = viewMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Pill size={22} /> Medications
          </h1>
        </div>
        <label className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', margin: 0 }}>
          {scanning
            ? <Loader2 size={16} style={{ animation: 'spin-anim 1s linear infinite' }} />
            : <Camera size={16} />}
          {scanning ? 'Reading label…' : 'Scan Label'}
          <input type="file" accept="image/*" capture="environment" onChange={scanLabel}
            style={{ display: 'none' }} disabled={scanning} />
        </label>
      </div>

      {/* ── Log intake (left) + calendar & history (right) ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 16, alignItems: 'start' }}>
        {/* Log New Medication Intake */}
        <div className="card">
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 0 }}>
            <Plus size={18} /> Log New Medication Intake
          </h3>
          {/* ── Say it in words ── */}
          <div data-testid="intake-intent" style={{ marginBottom: 14, padding: 12, borderRadius: 10, background: '#f6f4ff' }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <input className="form-input" style={{ flex: 1 }}
                placeholder='e.g. "I take Calcitriol" or "took 2 tablets of calcium carbonate"'
                value={intakeText} onChange={(e) => setIntakeText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); readIntake(); } }} />
              <button type="button" className="btn btn-secondary" onClick={readIntake}
                disabled={intakeBusy || !intakeText.trim()}>
                {intakeBusy ? 'Reading…' : 'Read this'}
              </button>
            </div>

            {intakeError && (
              <p data-testid="intake-error" style={{ color: '#c62828', fontSize: 13, marginTop: 8 }}>{intakeError}</p>
            )}

            {proposal?.medication_name && (
              <div data-testid="intake-proposal" style={{ marginTop: 10, fontSize: 14 }}>
                <strong>{proposal.medication_name}</strong>
                {proposal.dose_amount != null && (
                  <> — {proposal.dose_amount}{proposal.dose_unit ? ` ${proposal.dose_unit}` : ''}</>
                )}
                {/* Provenance is shown, always. A dose lifted from history that
                    arrives without saying where it came from is indistinguishable
                    from one the app invented. */}
                {proposal.provenance && (
                  <div style={{ color: '#666', fontSize: 12, marginTop: 2 }}>{proposal.provenance}</div>
                )}
                {(proposal.findings || []).map((f, i) => (
                  <div key={i} data-testid="intake-finding"
                    style={{ color: f.level === 'error' ? '#c62828' : '#856404', fontSize: 12, marginTop: 4 }}>
                    {f.message}
                  </div>
                ))}
                <button type="button" className="btn btn-primary btn-sm" style={{ marginTop: 8 }}
                  onClick={acceptProposal}>
                  {proposal.dose_amount != null ? 'Use this' : 'Fill the name'}
                </button>
              </div>
            )}
          </div>

          <form onSubmit={submitLog}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Date</label>
                <input className="form-input" type="date" value={log.log_date} onChange={(e) => up('log_date', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Time</label>
                <input className="form-input" type="time" value={log.log_time} onChange={(e) => up('log_time', e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Medication</label>
              <input className="form-input" list="med-catalog" placeholder="Select from profile or add new"
                value={log.medication_name} onChange={(e) => up('medication_name', e.target.value)} />
              <datalist id="med-catalog">
                {/* ACTIVE only. The picker used to offer every row, so a patient
                    whose profile held two 2017 EHR imports (both is_active=false,
                    stopped nine years ago) was shown those as their only two
                    choices for "what are you taking today". A stopped
                    prescription is a historical fact, not an option. They remain
                    visible, labelled, in Prescriptions below. */}
                {activeMeds.map((m) => <option key={m.id} value={m.name} />)}
              </datalist>
              {onlyStaleMeds && (
                <p data-testid="stale-meds-hint" style={{ fontSize: 12, color: '#856404', marginTop: 6 }}>
                  Your profile has {meds.length} prescription{meds.length === 1 ? '' : 's'}, but
                  {meds.length === 1 ? ' it is' : ' all of them are'} marked stopped — so
                  {meds.length === 1 ? ' it is' : ' none are'} offered above. Type the medication,
                  or add a current one under <strong>Prescriptions</strong>.
                </p>
              )}
            </div>
            <div className="form-group">
              <label className="form-label">Dosage Taken</label>
              <input className="form-input" placeholder="e.g., 1 pill, 10mg" value={log.dosage} onChange={(e) => up('dosage', e.target.value)} />
            </div>

            <fieldset style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 8, padding: 12, marginBottom: 12 }}>
              <legend style={{ fontSize: '.85rem', fontWeight: 600, padding: '0 6px', display: 'flex', alignItems: 'center', gap: 8 }}>
                Pre-Medication Vitals (optional)
                <button type="button" onClick={handleTempToggle}
                  style={{ fontSize: '.65rem', padding: '1px 6px', borderRadius: 8, border: '1px solid var(--primary)', background: 'transparent', color: 'var(--primary)', cursor: 'pointer' }}
                  title="Toggle temperature unit (stored in °C)">temp: {temp.label}</button>
              </legend>
              <div className="form-row">
                <div className="form-group"><label className="form-label">Systolic BP</label>
                  <input className="form-input" type="number" placeholder="120" value={log.pre_systolic_bp} onChange={(e) => up('pre_systolic_bp', e.target.value)} /></div>
                <div className="form-group"><label className="form-label">Diastolic BP</label>
                  <input className="form-input" type="number" placeholder="80" value={log.pre_diastolic_bp} onChange={(e) => up('pre_diastolic_bp', e.target.value)} /></div>
                <div className="form-group"><label className="form-label">Heart Rate</label>
                  <input className="form-input" type="number" placeholder="70" value={log.pre_heart_rate} onChange={(e) => up('pre_heart_rate', e.target.value)} /></div>
                <div className="form-group"><label className="form-label">Temp ({temp.label})</label>
                  <input className="form-input" type="number" step="0.1" placeholder={temp.unit === 'F' ? '98.6' : '37.0'} value={log.pre_temp} onChange={(e) => up('pre_temp', e.target.value)} /></div>
              </div>
            </fieldset>

            <fieldset style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 8, padding: 12, marginBottom: 12 }}>
              <legend style={{ fontSize: '.85rem', fontWeight: 600, padding: '0 6px' }}>Post-Medication Vitals (optional)</legend>
              <div className="form-row">
                <div className="form-group"><label className="form-label">Systolic BP</label>
                  <input className="form-input" type="number" placeholder="118" value={log.post_systolic_bp} onChange={(e) => up('post_systolic_bp', e.target.value)} /></div>
                <div className="form-group"><label className="form-label">Diastolic BP</label>
                  <input className="form-input" type="number" placeholder="78" value={log.post_diastolic_bp} onChange={(e) => up('post_diastolic_bp', e.target.value)} /></div>
                <div className="form-group"><label className="form-label">Heart Rate</label>
                  <input className="form-input" type="number" placeholder="68" value={log.post_heart_rate} onChange={(e) => up('post_heart_rate', e.target.value)} /></div>
                <div className="form-group"><label className="form-label">Temp ({temp.label})</label>
                  <input className="form-input" type="number" step="0.1" placeholder={temp.unit === 'F' ? '98.6' : '37.0'} value={log.post_temp} onChange={(e) => up('post_temp', e.target.value)} /></div>
              </div>
            </fieldset>

            <div className="form-group">
              <label className="form-label">Notes (optional)</label>
              <textarea className="form-input" rows={2} placeholder="e.g., Taken with food" value={log.notes} onChange={(e) => up('notes', e.target.value)} />
            </div>
            <button className="btn btn-primary" type="submit" disabled={savingLog}>
              {savingLog ? 'Saving…' : 'Add Medication Entry'}
            </button>
          </form>
        </div>

        {/* Calendar + history */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>📅 Select Date</h3>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <button type="button" className="btn btn-outline btn-sm" onClick={() => shiftMonth(-1)}><ChevronLeft size={16} /></button>
              <strong>{monthLabel}</strong>
              <button type="button" className="btn btn-outline btn-sm" onClick={() => shiftMonth(1)}><ChevronRight size={16} /></button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, textAlign: 'center' }}>
              {WEEKDAYS.map((w) => <div key={w} style={{ fontSize: '.72rem', color: 'var(--text-secondary)', padding: 4 }}>{w}</div>)}
              {cells.map((c, i) => c === null ? <div key={`b${i}`} /> : (
                <button key={c.ds} type="button" onClick={() => setSelectedDate(c.ds)}
                  style={{
                    position: 'relative', padding: '8px 0', border: 'none', borderRadius: 8, cursor: 'pointer',
                    background: c.ds === selectedDate ? 'var(--primary)' : 'transparent',
                    color: c.ds === selectedDate ? '#fff' : 'inherit', fontSize: '.85rem',
                  }}>
                  {c.d}
                  {datesWithEntries.has(c.ds) && (
                    <span style={{ position: 'absolute', bottom: 3, left: '50%', transform: 'translateX(-50%)', width: 5, height: 5, borderRadius: '50%', background: c.ds === selectedDate ? '#fff' : 'var(--primary)' }} />
                  )}
                </button>
              ))}
            </div>
            <p style={{ fontSize: '.72rem', color: 'var(--text-secondary)', marginTop: 8, marginBottom: 0 }}>
              Dates with a <span style={{ color: 'var(--primary)' }}>●</span> have logged entries.
            </p>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Medications for {fmtLong(selectedDate)}</h3>
            {dayDoses.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)' }}>No intake logged for this date.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {dayDoses.map((d) => {
                  const note = cleanNotes(d.notes);
                  const t = doseTime(d);
                  return (
                    <div key={d.id} className="card" style={{ margin: 0, border: '1px solid var(--border,#e5e7eb)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <strong>{t ? `${t} – ` : ''}{d.medication_name}</strong>
                        <button className="btn btn-danger btn-sm" onClick={() => deleteDose(d.id)} title="Delete"><Trash2 size={14} /></button>
                      </div>
                      <div style={{ fontSize: '.85rem', color: 'var(--text-secondary)' }}>{d.dose_amount} {d.dose_unit}</div>
                      {(d.pre_systolic_bp || d.pre_heart_rate || d.pre_temperature_c != null) && (
                        <div style={{ fontSize: '.78rem', marginTop: 4 }}>
                          Pre: {d.pre_systolic_bp ?? '–'}/{d.pre_diastolic_bp ?? '–'} mmHg, HR {d.pre_heart_rate ?? '–'}
                          {d.pre_temperature_c != null && `, ${temp.fmt(d.pre_temperature_c)}`}
                        </div>
                      )}
                      {(d.post_systolic_bp || d.post_heart_rate || d.post_temperature_c != null) && (
                        <div style={{ fontSize: '.78rem' }}>
                          Post: {d.post_systolic_bp ?? '–'}/{d.post_diastolic_bp ?? '–'} mmHg, HR {d.post_heart_rate ?? '–'}
                          {d.post_temperature_c != null && `, ${temp.fmt(d.post_temperature_c)}`}
                        </div>
                      )}
                      {note && <div style={{ fontSize: '.82rem', marginTop: 4 }}>{note}</div>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Prescriptions catalog (secondary, collapsible) ── */}
      <div className="card" style={{ marginTop: '1.5rem' }}>
        <button type="button" onClick={() => setShowRx((v) => !v)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem', fontWeight: 600, color: 'var(--primary)', padding: 0 }}>
          {showRx ? '▾' : '▸'} Prescriptions {meds.length > 0 && `(${activeMeds.length} active of ${meds.length})`}
        </button>
        {showRx && (
          <div style={{ marginTop: 12 }}>
            <form onSubmit={saveRx}>
              <div className="form-row">
                <div className="form-group"><label className="form-label">Medication Name</label>
                  <input className="form-input" value={rx.name} onChange={(e) => setRx({ ...rx, name: e.target.value })} required /></div>
                <div className="form-group"><label className="form-label">Dosage</label>
                  <input className="form-input" value={rx.dosage} onChange={(e) => setRx({ ...rx, dosage: e.target.value })} /></div>
                <div className="form-group"><label className="form-label">Unit</label>
                  <input className="form-input" value={rx.dosage_unit} placeholder="mg, ml…" onChange={(e) => setRx({ ...rx, dosage_unit: e.target.value })} /></div>
              </div>
              <div className="form-row">
                <div className="form-group"><label className="form-label">Frequency</label>
                  <input className="form-input" value={rx.frequency} placeholder="e.g., twice daily" onChange={(e) => setRx({ ...rx, frequency: e.target.value })} /></div>
                <div className="form-group"><label className="form-label">Reason</label>
                  <input className="form-input" value={rx.reason} onChange={(e) => setRx({ ...rx, reason: e.target.value })} /></div>
              </div>
              <button className="btn btn-primary btn-sm" type="submit">Save Prescription</button>
            </form>
            <table className="table" style={{ marginTop: 12 }}>
              <thead><tr><th>Name</th><th>Dosage</th><th>Frequency</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {meds.map((m) => (
                  <tr key={m.id}>
                    <td>{m.name}{m.source && (
                      <span title={`Imported from ${m.source}`}
                        style={{ marginLeft: 6, fontSize: '.62rem', fontWeight: 700, padding: '1px 6px',
                          borderRadius: 8, background: '#fff3cd', color: '#856404', whiteSpace: 'nowrap' }}>
                        ⤵ Imported
                      </span>)}</td><td>{m.dosage} {m.dosage_unit}</td><td>{m.frequency ?? '-'}</td>
                    <td>{m.is_active ? '🟢 Active' : '⚪ Inactive'}</td>
                    <td><button className="btn btn-danger btn-sm" onClick={() => deleteRx(m.id)}><Trash2 size={14} /></button></td>
                  </tr>
                ))}
                {meds.length === 0 && <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>No prescriptions yet</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
