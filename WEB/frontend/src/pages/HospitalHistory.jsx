// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

import React, { useState, useEffect } from 'react';
import api from '../services/api';
import BackButton from '../components/BackButton';
import { t } from '../i18n';

// Hospital stays and surgical procedures.
//
// The page leads with LASTING EFFECTS rather than with a list of admissions,
// because that is the half a patient and a clinician actually act on: a
// parathyroidectomy explains a calcium requirement that no guideline default
// can express, and it stays true decades after the admission is history.
//
// `stays` and `procedures` are drawn as SEPARATE sections on purpose. A
// procedure may have no admission at all — day-case surgery, or anything
// recorded years after the fact — so a page that only walked stays and their
// nested procedures would silently omit exactly those operations.

const emptyStay = {
  admitted_at: '',
  discharged_at: '',
  facility_name: '',
  ward: '',
  room: '',
  admission_type: '',
  status: '',
  reason: '',
  primary_diagnosis: '',
  icd10_code: '',
  attending_physician: '',
  discharge_disposition: '',
  complications: '',
  notes: '',
};

const emptyProcedure = {
  name: '',
  code: '',
  code_system: '',
  body_site: '',
  laterality: '',
  performed_at: '',
  hospitalization_id: '',
  surgeon: '',
  anesthesia_type: '',
  outcome: '',
  complications: '',
  ongoing_effects: '',
  notes: '',
};

const HospitalHistory = () => {
  const [history, setHistory] = useState({ stays: [], procedures: [], lasting_effects: [] });
  const [stays, setStays] = useState([]);
  const [loading, setLoading] = useState(true);
  // Separate from the data on purpose: a failed fetch must never render as
  // "no hospital history recorded" (CLAUDE.md §3aa — an error is not an
  // empty state).
  const [loadError, setLoadError] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const [showStayForm, setShowStayForm] = useState(false);
  const [showProcedureForm, setShowProcedureForm] = useState(false);
  const [stayForm, setStayForm] = useState(emptyStay);
  const [procedureForm, setProcedureForm] = useState(emptyProcedure);

  const admissionTypes = [
    { value: '', label: t('Hospital.not_stated') },
    { value: 'emergency', label: t('Hospital.emergency') },
    { value: 'elective', label: t('Hospital.elective') },
    { value: 'urgent', label: t('Hospital.urgent') },
    { value: 'observation', label: t('Hospital.observation') },
    { value: 'day_case', label: t('Hospital.day_case') },
    { value: 'maternity', label: t('Hospital.maternity') },
    { value: 'rehabilitation', label: t('Hospital.rehabilitation') },
    { value: 'other', label: t('Hospital.other') },
  ];

  const statuses = [
    { value: '', label: t('Hospital.not_stated') },
    { value: 'planned', label: t('Hospital.planned') },
    { value: 'in_progress', label: t('Hospital.in_progress') },
    { value: 'discharged', label: t('Hospital.discharged') },
    { value: 'transferred', label: t('Hospital.transferred') },
    { value: 'cancelled', label: t('Hospital.cancelled') },
  ];

  const outcomes = [
    { value: '', label: t('Hospital.not_stated') },
    { value: 'successful', label: t('Hospital.successful') },
    { value: 'partially_successful', label: t('Hospital.partially_successful') },
    { value: 'unsuccessful', label: t('Hospital.unsuccessful') },
    { value: 'complicated', label: t('Hospital.complicated') },
    { value: 'abandoned', label: t('Hospital.abandoned') },
    { value: 'unknown', label: t('Hospital.unknown') },
  ];

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [h, s] = await Promise.all([
        api.get('/hospital/history'),
        api.get('/hospital/stays'),
      ]);
      setHistory(h.data || { stays: [], procedures: [], lasting_effects: [] });
      setStays(s.data || []);
      setLoadError(null);
    } catch (e) {
      setLoadError(e?.response?.data?.detail || e?.message || t('Hospital.load_failed'));
    } finally {
      setLoading(false);
    }
  };

  // The API refuses an impossible pair (a discharge before the admission) with
  // a 422. Show the server's own reason instead of a generic failure — a guard
  // that cannot explain itself gets blamed for the thing it did not do (§3aj).
  const describeError = (e) => {
    const detail = e?.response?.data?.detail;
    if (Array.isArray(detail)) return detail.map((d) => d.msg || String(d)).join('; ');
    if (typeof detail === 'string') return detail;
    return e?.message || t('Hospital.save_failed');
  };

  // An empty string must not be sent as a value. `admitted_at` is required and
  // the enums reject '', so blanks are dropped rather than transmitted.
  const prune = (obj) => Object.fromEntries(
    Object.entries(obj).filter(([, v]) => v !== '' && v !== null && v !== undefined),
  );

  const submitStay = async (e) => {
    e.preventDefault();
    setSaveError(null);
    try {
      await api.post('/hospital/stays', prune(stayForm));
      setStayForm(emptyStay);
      setShowStayForm(false);
      await load();
    } catch (err) {
      setSaveError(describeError(err));
    }
  };

  const submitProcedure = async (e) => {
    e.preventDefault();
    setSaveError(null);
    try {
      const payload = prune(procedureForm);
      if (payload.hospitalization_id) {
        payload.hospitalization_id = Number(payload.hospitalization_id);
      }
      await api.post('/hospital/procedures', payload);
      setProcedureForm(emptyProcedure);
      setShowProcedureForm(false);
      await load();
    } catch (err) {
      setSaveError(describeError(err));
    }
  };

  const removeStay = async (id) => {
    setSaveError(null);
    try {
      await api.delete(`/hospital/stays/${id}`);
      await load();
    } catch (err) {
      setSaveError(describeError(err));
    }
  };

  const field = (label, value, onChange, type = 'text') => (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-gray-300 rounded-lg px-3 py-2"
      />
    </div>
  );

  const picker = (label, value, onChange, options) => (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-gray-300 rounded-lg px-3 py-2"
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <BackButton />
      <h1 className="text-2xl font-bold text-gray-900 mb-1">{t('Hospital.title')}</h1>
      <p className="text-sm text-gray-600 mb-6">{t('Hospital.subtitle')}</p>

      {loadError && (
        <div className="mb-6 rounded-lg border border-red-300 bg-red-50 p-4">
          <p className="font-medium text-red-800">{t('Hospital.could_not_load')}</p>
          <p className="text-sm text-red-700 mt-1">{loadError}</p>
          <button onClick={load} className="mt-2 text-sm underline text-red-800">
            {t('Hospital.try_again')}
          </button>
        </div>
      )}

      {saveError && (
        <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <p className="text-sm text-amber-900">{saveError}</p>
        </div>
      )}

      {/* What past surgery STILL does to this patient. First, because it is
          what any advice about calcium, phosphate or bone depends on. */}
      {history.lasting_effects?.length > 0 && (
        <section className="mb-8 rounded-lg border border-indigo-300 bg-indigo-50 p-4">
          <h2 className="font-semibold text-indigo-900 mb-2">
            {t('Hospital.lasting_effects')}
          </h2>
          <p className="text-xs text-indigo-800 mb-3">{t('Hospital.lasting_effects_note')}</p>
          <ul className="space-y-1">
            {history.lasting_effects.map((e, i) => (
              <li key={i} className="text-sm text-indigo-900">• {e}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="flex flex-wrap gap-3 mb-6">
        <button
          onClick={() => { setShowStayForm((v) => !v); setShowProcedureForm(false); }}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm"
        >
          {t('Hospital.add_stay')}
        </button>
        <button
          onClick={() => { setShowProcedureForm((v) => !v); setShowStayForm(false); }}
          className="px-4 py-2 rounded-lg bg-white border border-gray-300 text-sm"
        >
          {t('Hospital.add_procedure')}
        </button>
      </div>

      {showStayForm && (
        <form onSubmit={submitStay} className="mb-8 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="font-semibold mb-3">{t('Hospital.add_stay')}</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {field(t('Hospital.admitted'), stayForm.admitted_at,
              (v) => setStayForm({ ...stayForm, admitted_at: v }), 'datetime-local')}
            {field(t('Hospital.discharged'), stayForm.discharged_at,
              (v) => setStayForm({ ...stayForm, discharged_at: v }), 'datetime-local')}
            {field(t('Hospital.facility'), stayForm.facility_name,
              (v) => setStayForm({ ...stayForm, facility_name: v }))}
            {picker(t('Hospital.admission_type'), stayForm.admission_type,
              (v) => setStayForm({ ...stayForm, admission_type: v }), admissionTypes)}
            {picker(t('Hospital.status'), stayForm.status,
              (v) => setStayForm({ ...stayForm, status: v }), statuses)}
            {field(t('Hospital.reason'), stayForm.reason,
              (v) => setStayForm({ ...stayForm, reason: v }))}
            {field(t('Hospital.diagnosis'), stayForm.primary_diagnosis,
              (v) => setStayForm({ ...stayForm, primary_diagnosis: v }))}
            {field(t('Hospital.attending'), stayForm.attending_physician,
              (v) => setStayForm({ ...stayForm, attending_physician: v }))}
          </div>
          <div className="mt-4 flex gap-3">
            <button type="submit" className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm">
              {t('common.save')}
            </button>
            <button
              type="button"
              onClick={() => { setShowStayForm(false); setStayForm(emptyStay); }}
              className="px-4 py-2 rounded-lg border border-gray-300 text-sm"
            >
              {t('common.cancel')}
            </button>
          </div>
        </form>
      )}

      {showProcedureForm && (
        <form onSubmit={submitProcedure} className="mb-8 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="font-semibold mb-1">{t('Hospital.add_procedure')}</h2>
          {/* Stated plainly, because this is the case most records cannot hold. */}
          <p className="text-xs text-gray-600 mb-3">{t('Hospital.procedure_no_stay_note')}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            {field(t('Hospital.procedure_name'), procedureForm.name,
              (v) => setProcedureForm({ ...procedureForm, name: v }))}
            {field(t('Hospital.performed'), procedureForm.performed_at,
              (v) => setProcedureForm({ ...procedureForm, performed_at: v }), 'datetime-local')}
            {field(t('Hospital.code'), procedureForm.code,
              (v) => setProcedureForm({ ...procedureForm, code: v }))}
            {/* The code is meaningless without the vocabulary that issued it:
                ICD-10-PCS, CPT, SNOMED and ICHI are different systems (§3ad). */}
            {field(t('Hospital.code_system'), procedureForm.code_system,
              (v) => setProcedureForm({ ...procedureForm, code_system: v }))}
            {field(t('Hospital.body_site'), procedureForm.body_site,
              (v) => setProcedureForm({ ...procedureForm, body_site: v }))}
            {picker(t('Hospital.outcome'), procedureForm.outcome,
              (v) => setProcedureForm({ ...procedureForm, outcome: v }), outcomes)}
            {field(t('Hospital.surgeon'), procedureForm.surgeon,
              (v) => setProcedureForm({ ...procedureForm, surgeon: v }))}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('Hospital.during_stay')}
              </label>
              <select
                value={procedureForm.hospitalization_id}
                onChange={(e) => setProcedureForm({ ...procedureForm, hospitalization_id: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2"
              >
                <option value="">{t('Hospital.no_stay')}</option>
                {stays.map((s) => (
                  <option key={s.id} value={s.id}>
                    {String(s.admitted_at).slice(0, 10)}
                    {s.facility_name ? ` — ${s.facility_name}` : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('Hospital.ongoing_effects')}
            </label>
            <p className="text-xs text-gray-600 mb-1">{t('Hospital.ongoing_effects_help')}</p>
            <textarea
              rows={2}
              value={procedureForm.ongoing_effects}
              onChange={(e) => setProcedureForm({ ...procedureForm, ongoing_effects: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </div>
          <div className="mt-4 flex gap-3">
            <button type="submit" className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm">
              {t('common.save')}
            </button>
            <button
              type="button"
              onClick={() => { setShowProcedureForm(false); setProcedureForm(emptyProcedure); }}
              className="px-4 py-2 rounded-lg border border-gray-300 text-sm"
            >
              {t('common.cancel')}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <p className="text-gray-600">{t('Hospital.loading')}</p>
      ) : (
        <>
          <section className="mb-8">
            <h2 className="font-semibold text-gray-900 mb-3">{t('Hospital.stays')}</h2>
            {history.stays?.length === 0 && !loadError && (
              <p className="text-sm text-gray-600">{t('Hospital.no_stays')}</p>
            )}
            <div className="space-y-3">
              {history.stays?.map((s, i) => (
                <div key={i} className="rounded-lg border border-gray-200 bg-white p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-gray-900">
                        {s.admitted}
                        {s.discharged ? ` → ${s.discharged}` : ''}
                        {/* `nights` is absent while a patient is still an
                            inpatient — never a length measured to today. */}
                        {s.nights != null ? ` · ${s.nights} ${t('Hospital.nights')}` : ''}
                      </p>
                      {s.facility && <p className="text-sm text-gray-700">{s.facility}</p>}
                      {s.reason && <p className="text-sm text-gray-600">{s.reason}</p>}
                      {s.diagnosis && <p className="text-sm text-gray-600">{s.diagnosis}</p>}
                      <p className="text-xs text-gray-500 mt-1">
                        {[s.admission_type, s.status, s.source].filter(Boolean).join(' · ')}
                      </p>
                    </div>
                  </div>
                  {s.procedures?.length > 0 && (
                    <ul className="mt-3 border-t border-gray-100 pt-3 space-y-1">
                      {s.procedures.map((p, j) => (
                        <li key={j} className="text-sm text-gray-800">
                          {p.name}
                          {p.performed ? ` · ${p.performed}` : ''}
                          {p.outcome ? ` · ${p.outcome}` : ''}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Raw rows, so a stay can be removed. Separate from the read view
              above, which comes from the canonical reader. */}
          {stays.length > 0 && (
            <section className="mb-8">
              <h2 className="font-semibold text-gray-900 mb-3">{t('Hospital.manage_stays')}</h2>
              <div className="space-y-2">
                {stays.map((s) => (
                  <div key={s.id} className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-2">
                    <span className="text-sm text-gray-800">
                      {String(s.admitted_at).slice(0, 10)}
                      {s.facility_name ? ` — ${s.facility_name}` : ''}
                    </span>
                    <button
                      onClick={() => removeStay(s.id)}
                      className="text-sm text-red-700 underline"
                    >
                      {t('common.delete')}
                    </button>
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-2">{t('Hospital.delete_keeps_procedures')}</p>
            </section>
          )}

          <section>
            <h2 className="font-semibold text-gray-900 mb-1">{t('Hospital.all_procedures')}</h2>
            <p className="text-xs text-gray-600 mb-3">{t('Hospital.all_procedures_note')}</p>
            {history.procedures?.length === 0 && !loadError && (
              <p className="text-sm text-gray-600">{t('Hospital.no_procedures')}</p>
            )}
            <div className="space-y-3">
              {history.procedures?.map((p, i) => (
                <div key={i} className="rounded-lg border border-gray-200 bg-white p-4">
                  <p className="font-medium text-gray-900">{p.name}</p>
                  <p className="text-sm text-gray-600">
                    {[p.performed, p.body_site, p.outcome].filter(Boolean).join(' · ')}
                  </p>
                  {p.code && (
                    <p className="text-xs text-gray-500">
                      {p.code}{p.code_system ? ` (${p.code_system})` : ''}
                    </p>
                  )}
                  <p className="text-xs text-gray-500 mt-1">
                    {p.admission
                      ? `${t('Hospital.during')} ${p.admission}`
                      : t('Hospital.no_stay_recorded')}
                  </p>
                  {p.ongoing_effects && (
                    <p className="mt-2 text-sm text-indigo-900 bg-indigo-50 rounded px-2 py-1">
                      {p.ongoing_effects}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
};

export default HospitalHistory;
