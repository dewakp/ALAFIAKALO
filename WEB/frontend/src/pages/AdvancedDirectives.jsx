import { useState, useEffect } from 'react';
import api from '../services/api';
import { FileHeart, Save, Edit, Trash2 } from 'lucide-react';
import BackButton from '../components/BackButton';
import { t } from '../i18n';

const yesNo = [
  { value: '', get label() { return t('AdvancedDirectives.not_specified'); } },
  { value: 'yes', get label() { return t('AdvancedDirectives.yes'); } },
  { value: 'no', get label() { return t('AdvancedDirectives.no'); } },
  { value: 'let_agent_decide', get label() { return t('AdvancedDirectives.let_agent_decide'); } },
];

const organOptions = ['all', 'heart', 'kidneys', 'liver', 'lungs', 'none'];

export default function AdvancedDirectives() {
  const [directive, setDirective] = useState(null);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(emptyForm());

  useEffect(() => { loadDirective(); }, []);

  function emptyForm() {
    return {
      primary_agent_name: '', primary_agent_relationship: '', primary_agent_phone: '', primary_agent_email: '', primary_agent_address: '',
      alternate_agent_name: '', alternate_agent_relationship: '', alternate_agent_phone: '', alternate_agent_email: '', alternate_agent_address: '',
      organ_donation: 'none', organ_donation_preferences: '',
      life_support: '', cpr: '', ventilator: '', feeding_tube: '', dialysis_directive: '', blood_transfusion: '',
      document_signed: false, document_date: '', witness_name: '', notarized: false, document_location: '',
      additional_instructions: '',
    };
  }

  async function loadDirective() {
    try {
      const { data } = await api.get('/advanced-directives/');
      setDirective(data);
      if (data) setForm(data);
    } catch (err) {
      if (err.response?.status !== 404) console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    try {
      if (directive) {
        await api.put('/advanced-directives/', form);
      } else {
        await api.post('/advanced-directives/', form);
      }
      setEditing(false);
      loadDirective();
    } catch (err) {
      alert(t('AdvancedDirectives.error_saving_directive'));
    }
  }

  async function handleDelete() {
    if (!confirm(t('AdvancedDirectives.delete_your_advanced_directive'))) return;
    try {
      await api.delete('/advanced-directives/');
      setDirective(null);
      setForm(emptyForm());
    } catch (err) {
      alert(t('AdvancedDirectives.error_deleting'));
    }
  }

  if (loading) return <div className="loading">{t('AdvancedDirectives.loading')}</div>;

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">{t('AdvancedDirectives.advanced_directives')}</h1>
        </div>
        {directive && !editing && (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn btn-primary" onClick={() => setEditing(true)}><Edit size={16} /> {t('AdvancedDirectives.edit')}</button>
            <button className="btn btn-secondary" style={{ color: 'var(--color-danger)' }} onClick={handleDelete}><Trash2 size={16} /> {t('AdvancedDirectives.delete')}</button>
          </div>
        )}
      </div>

      {!directive && !editing ? (
        <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>
          <FileHeart size={48} color="var(--color-text-secondary)" style={{ marginBottom: '1rem' }} />
          <h3>{t('AdvancedDirectives.no_advanced_directive_on_file')}</h3>
          <p style={{ color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>
            {t('AdvancedDirectives.create_your_advanced_directive_to')}
          </p>
          <button className="btn btn-primary" onClick={() => setEditing(true)}>{t('AdvancedDirectives.create_directive')}</button>
        </div>
      ) : editing ? (
        <form onSubmit={handleSubmit}>
          <Section title={t('AdvancedDirectives.primary_healthcare_agent')}>
            <Grid>
              <Field label={t('AdvancedDirectives.full_name')} value={form.primary_agent_name} onChange={v => setForm(p => ({ ...p, primary_agent_name: v }))} />
              <Field label={t('AdvancedDirectives.relationship')} value={form.primary_agent_relationship} onChange={v => setForm(p => ({ ...p, primary_agent_relationship: v }))} />
              <Field label={t('AdvancedDirectives.phone')} value={form.primary_agent_phone} onChange={v => setForm(p => ({ ...p, primary_agent_phone: v }))} />
              <Field label={t('AdvancedDirectives.email')} type="email" value={form.primary_agent_email} onChange={v => setForm(p => ({ ...p, primary_agent_email: v }))} />
              <Field label={t('AdvancedDirectives.address')} value={form.primary_agent_address} onChange={v => setForm(p => ({ ...p, primary_agent_address: v }))} span={2} />
            </Grid>
          </Section>

          <Section title={t('AdvancedDirectives.alternate_healthcare_agent')}>
            <Grid>
              <Field label={t('AdvancedDirectives.full_name')} value={form.alternate_agent_name} onChange={v => setForm(p => ({ ...p, alternate_agent_name: v }))} />
              <Field label={t('AdvancedDirectives.relationship')} value={form.alternate_agent_relationship} onChange={v => setForm(p => ({ ...p, alternate_agent_relationship: v }))} />
              <Field label={t('AdvancedDirectives.phone')} value={form.alternate_agent_phone} onChange={v => setForm(p => ({ ...p, alternate_agent_phone: v }))} />
              <Field label={t('AdvancedDirectives.email')} type="email" value={form.alternate_agent_email} onChange={v => setForm(p => ({ ...p, alternate_agent_email: v }))} />
            </Grid>
          </Section>

          <Section title={t('AdvancedDirectives.organ_donation')}>
            <Grid>
              <div className="form-group">
                <label className="form-label">{t('AdvancedDirectives.organ_donation')}</label>
                <select className="form-select" value={form.organ_donation}
                  onChange={e => setForm(p => ({ ...p, organ_donation: e.target.value }))}>
                  {organOptions.map(o => <option key={o} value={o}>{o.charAt(0).toUpperCase() + o.slice(1)}</option>)}
                </select>
              </div>
              <Field label={t('AdvancedDirectives.preferences_notes')} value={form.organ_donation_preferences}
                onChange={v => setForm(p => ({ ...p, organ_donation_preferences: v }))} />
            </Grid>
          </Section>

          <Section title={t('AdvancedDirectives.life_sustaining_treatment_preferences')}>
            <Grid cols={3}>
              {[
                ['life_support', 'Life Support'],
                ['cpr', 'CPR'],
                ['ventilator', 'Ventilator'],
                ['feeding_tube', 'Feeding Tube'],
                ['dialysis_directive', 'Dialysis'],
                ['blood_transfusion', 'Blood Transfusion'],
              ].map(([key, label]) => (
                <div className="form-group" key={key}>
                  <label className="form-label">{label}</label>
                  <select className="form-select" value={form[key] || ''}
                    onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}>
                    {yesNo.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
              ))}
            </Grid>
          </Section>

          <Section title={t('AdvancedDirectives.document_information')}>
            <Grid>
              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={form.document_signed}
                    onChange={e => setForm(p => ({ ...p, document_signed: e.target.checked }))} /> {t('AdvancedDirectives.document_signed')}
                </label>
              </div>
              <Field label={t('AdvancedDirectives.date_signed')} type="date" value={form.document_date || ''}
                onChange={v => setForm(p => ({ ...p, document_date: v }))} />
              <Field label={t('AdvancedDirectives.witness_name')} value={form.witness_name}
                onChange={v => setForm(p => ({ ...p, witness_name: v }))} />
              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={form.notarized}
                    onChange={e => setForm(p => ({ ...p, notarized: e.target.checked }))} /> {t('AdvancedDirectives.notarized')}
                </label>
              </div>
              <Field label={t('AdvancedDirectives.document_location')} value={form.document_location}
                onChange={v => setForm(p => ({ ...p, document_location: v }))} span={2} />
            </Grid>
          </Section>

          <Section title={t('AdvancedDirectives.additional_instructions')}>
            <div className="form-group">
              <textarea className="form-input" rows={3} value={form.additional_instructions || ''}
                onChange={e => setForm(p => ({ ...p, additional_instructions: e.target.value }))}
                placeholder={t('AdvancedDirectives.any_additional_healthcare_wishes_or')} />
            </div>
          </Section>

          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem' }}>
            <button type="submit" className="btn btn-primary"><Save size={16} /> {t('AdvancedDirectives.save_directive')}</button>
            <button type="button" className="btn btn-secondary" onClick={() => { setEditing(false); if (directive) setForm(directive); }}>{t('AdvancedDirectives.cancel')}</button>
          </div>
        </form>
      ) : (
        <DirectiveView directive={directive} />
      )}
    </div>
  );
}

function DirectiveView({ directive }) {
  const d = directive;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div className="card" style={{ padding: '1.25rem' }}>
        <h3 style={{ marginBottom: '0.75rem', color: 'var(--color-primary)' }}>{t('AdvancedDirectives.primary_healthcare_agent')}</h3>
        <InfoGrid items={[
          ['Name', d.primary_agent_name], ['Relationship', d.primary_agent_relationship],
          ['Phone', d.primary_agent_phone], ['Email', d.primary_agent_email],
          ['Address', d.primary_agent_address],
        ]} />
      </div>
      {d.alternate_agent_name && (
        <div className="card" style={{ padding: '1.25rem' }}>
          <h3 style={{ marginBottom: '0.75rem', color: 'var(--color-info)' }}>{t('AdvancedDirectives.alternate_healthcare_agent')}</h3>
          <InfoGrid items={[
            ['Name', d.alternate_agent_name], ['Relationship', d.alternate_agent_relationship],
            ['Phone', d.alternate_agent_phone], ['Email', d.alternate_agent_email],
          ]} />
        </div>
      )}
      <div className="card" style={{ padding: '1.25rem' }}>
        <h3 style={{ marginBottom: '0.75rem' }}>{t('AdvancedDirectives.treatment_preferences')}</h3>
        <InfoGrid items={[
          ['Life Support', d.life_support], ['CPR', d.cpr],
          ['Ventilator', d.ventilator], ['Feeding Tube', d.feeding_tube],
          ['Dialysis', d.dialysis_directive], ['Blood Transfusion', d.blood_transfusion],
          ['Organ Donation', d.organ_donation],
        ]} />
      </div>
      <div className="card" style={{ padding: '1.25rem' }}>
        <h3 style={{ marginBottom: '0.75rem' }}>{t('AdvancedDirectives.document_status')}</h3>
        <InfoGrid items={[
          ['Signed', d.document_signed ? 'Yes' : 'No'],
          ['Date', d.document_date], ['Witness', d.witness_name],
          ['Notarized', d.notarized ? 'Yes' : 'No'],
          ['Location', d.document_location],
        ]} />
      </div>
      {d.additional_instructions && (
        <div className="card" style={{ padding: '1.25rem' }}>
          <h3 style={{ marginBottom: '0.5rem' }}>{t('AdvancedDirectives.additional_instructions')}</h3>
          <p>{d.additional_instructions}</p>
        </div>
      )}
    </div>
  );
}

function InfoGrid({ items }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.5rem', fontSize: '0.9rem' }}>
      {items.filter(([, v]) => v).map(([label, value]) => (
        <div key={label}><strong>{label}:</strong> {value}</div>
      ))}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
      <h3 style={{ marginBottom: '0.75rem' }}>{title}</h3>
      {children}
    </div>
  );
}

function Grid({ children, cols = 2 }) {
  return <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: '1rem' }}>{children}</div>;
}

function Field({ label, value, onChange, type = 'text', span = 1 }) {
  return (
    <div className="form-group" style={span > 1 ? { gridColumn: `span ${span}` } : {}}>
      <label className="form-label">{label}</label>
      <input type={type} className="form-input" value={value || ''} onChange={e => onChange(e.target.value)} />
    </div>
  );
}
