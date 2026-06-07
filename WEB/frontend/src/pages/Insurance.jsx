import { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus, Shield, Star, Trash2, ChevronDown, ChevronRight, Globe, X, Edit3 } from 'lucide-react';
import BackButton from '../components/BackButton';

const REGIONS = [
  { code: 'north_america', name: 'North America', emoji: '🌎' },
  { code: 'europe', name: 'Europe', emoji: '🌍' },
  { code: 'south_asia', name: 'South Asia', emoji: '🌏' },
  { code: 'africa', name: 'Africa', emoji: '🌍' },
  { code: 'middle_east', name: 'Middle East', emoji: '🌍' },
];

const PLAN_TYPES = ['HMO', 'PPO', 'EPO', 'POS', 'HDHP', 'Indemnity', 'Government', 'Universal', 'Other'];
const RELATIONSHIPS = ['self', 'spouse', 'child', 'parent', 'other'];

export default function Insurance() {
  const [plans, setPlans] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingPlan, setEditingPlan] = useState(null);
  const [regionCountries, setRegionCountries] = useState({});
  const [providers, setProviders] = useState([]);

  // Form state
  const [region, setRegion] = useState('');
  const [countryCode, setCountryCode] = useState('');
  const [countryName, setCountryName] = useState('');
  const [providerCode, setProviderCode] = useState('');
  const [providerName, setProviderName] = useState('');
  const [policyNumber, setPolicyNumber] = useState('');
  const [groupNumber, setGroupNumber] = useState('');
  const [memberId, setMemberId] = useState('');
  const [planName, setPlanName] = useState('');
  const [planType, setPlanType] = useState('');
  const [coverageStart, setCoverageStart] = useState('');
  const [coverageEnd, setCoverageEnd] = useState('');
  const [isPrimary, setIsPrimary] = useState(false);
  const [subscriberName, setSubscriberName] = useState('');
  const [subscriberRelationship, setSubscriberRelationship] = useState('self');
  const [insurancePhone, setInsurancePhone] = useState('');
  const [notes, setNotes] = useState('');

  useEffect(() => { loadPlans(); loadRegions(); }, []);

  async function loadPlans() { const { data } = await api.get('/insurance/'); setPlans(data); }
  async function loadRegions() { const { data } = await api.get('/insurance/regions'); setRegionCountries(data); }

  async function loadProviders(cc) {
    try { const { data } = await api.get(`/insurance/providers/${cc}`); setProviders(data); }
    catch { setProviders([]); }
  }

  function resetForm() {
    setRegion(''); setCountryCode(''); setCountryName(''); setProviderCode(''); setProviderName('');
    setPolicyNumber(''); setGroupNumber(''); setMemberId(''); setPlanName(''); setPlanType('');
    setCoverageStart(''); setCoverageEnd(''); setIsPrimary(false); setSubscriberName('');
    setSubscriberRelationship('self'); setInsurancePhone(''); setNotes('');
    setProviders([]); setEditingPlan(null);
  }

  function startEdit(plan) {
    setEditingPlan(plan);
    setRegion(plan.region); setCountryCode(plan.country_code); setCountryName(plan.country_name);
    setProviderCode(plan.provider_code); setProviderName(plan.provider_name);
    setPolicyNumber(plan.policy_number || ''); setGroupNumber(plan.group_number || '');
    setMemberId(plan.member_id || ''); setPlanName(plan.plan_name || '');
    setPlanType(plan.plan_type || ''); setCoverageStart(plan.coverage_start || '');
    setCoverageEnd(plan.coverage_end || ''); setIsPrimary(plan.is_primary);
    setSubscriberName(plan.subscriber_name || '');
    setSubscriberRelationship(plan.subscriber_relationship || 'self');
    setInsurancePhone(plan.insurance_phone || ''); setNotes(plan.notes || '');
    loadProviders(plan.country_code);
    setShowForm(true);
  }

  function handleRegionChange(r) {
    setRegion(r); setCountryCode(''); setCountryName(''); setProviderCode(''); setProviderName(''); setProviders([]);
  }

  function handleCountryChange(cc) {
    const countries = regionCountries[region] || [];
    const country = countries.find(c => c.code === cc);
    setCountryCode(cc); setCountryName(country?.name || cc);
    setProviderCode(''); setProviderName('');
    loadProviders(cc);
  }

  function handleProviderChange(code) {
    const p = providers.find(pr => pr.code === code);
    setProviderCode(code); setProviderName(p?.name || code);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const body = {
      region, country_code: countryCode, country_name: countryName,
      provider_code: providerCode, provider_name: providerName,
      policy_number: policyNumber || null, group_number: groupNumber || null,
      member_id: memberId || null, plan_name: planName || null,
      plan_type: planType || null, coverage_start: coverageStart || null,
      coverage_end: coverageEnd || null, is_primary: isPrimary,
      subscriber_name: subscriberName || null,
      subscriber_relationship: subscriberRelationship || null,
      insurance_phone: insurancePhone || null, notes: notes || null,
      is_active: true,
    };
    if (editingPlan) {
      await api.patch(`/insurance/${editingPlan.id}`, body);
    } else {
      await api.post('/insurance/', body);
    }
    setShowForm(false); resetForm(); loadPlans();
  }

  async function handleDelete(id) {
    if (!confirm('Remove this insurance plan?')) return;
    await api.delete(`/insurance/${id}`); loadPlans();
  }

  async function handleSetPrimary(id) {
    await api.post(`/insurance/${id}/set-primary`); loadPlans();
  }

  const activePlans = plans.filter(p => p.is_active);
  const inactivePlans = plans.filter(p => !p.is_active);

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title"><Shield size={28} style={{ marginRight: 8, verticalAlign: 'middle' }} />Insurance Plans</h1>
        </div>
        <button className="btn btn-primary" onClick={() => { resetForm(); setShowForm(!showForm); }}>
          {showForm ? <><X size={18} /> Cancel</> : <><Plus size={18} /> Add Plan</>}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>{editingPlan ? 'Edit Insurance Plan' : 'Add Insurance Plan'}</h3>
          <form onSubmit={handleSubmit}>
            {/* Region & Country */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label className="form-label">Region *</label>
                <select className="form-input" value={region} onChange={e => handleRegionChange(e.target.value)} required>
                  <option value="">Select Region</option>
                  {REGIONS.map(r => <option key={r.code} value={r.code}>{r.emoji} {r.name}</option>)}
                </select>
              </div>
              <div>
                <label className="form-label">Country *</label>
                <select className="form-input" value={countryCode} onChange={e => handleCountryChange(e.target.value)} required disabled={!region}>
                  <option value="">Select Country</option>
                  {(regionCountries[region] || []).map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className="form-label">Insurance Provider *</label>
                <select className="form-input" value={providerCode} onChange={e => handleProviderChange(e.target.value)} required disabled={!countryCode}>
                  <option value="">Select Provider</option>
                  {providers.map(p => <option key={p.code} value={p.code}>{p.name}</option>)}
                </select>
              </div>
            </div>

            {/* Policy details */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label className="form-label">Policy / ID Number</label>
                <input className="form-input" value={policyNumber} onChange={e => setPolicyNumber(e.target.value)} placeholder="e.g. 1EG4-TE5-MK72" />
              </div>
              <div>
                <label className="form-label">Group Number</label>
                <input className="form-input" value={groupNumber} onChange={e => setGroupNumber(e.target.value)} />
              </div>
              <div>
                <label className="form-label">Member ID</label>
                <input className="form-input" value={memberId} onChange={e => setMemberId(e.target.value)} />
              </div>
              <div>
                <label className="form-label">Plan Type</label>
                <select className="form-input" value={planType} onChange={e => setPlanType(e.target.value)}>
                  <option value="">Select</option>
                  {PLAN_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            </div>

            {/* Plan name & coverage dates */}
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label className="form-label">Plan Name</label>
                <input className="form-input" value={planName} onChange={e => setPlanName(e.target.value)} placeholder="e.g. Gold PPO" />
              </div>
              <div>
                <label className="form-label">Coverage Start</label>
                <input className="form-input" type="date" value={coverageStart} onChange={e => setCoverageStart(e.target.value)} />
              </div>
              <div>
                <label className="form-label">Coverage End</label>
                <input className="form-input" type="date" value={coverageEnd} onChange={e => setCoverageEnd(e.target.value)} />
              </div>
            </div>

            {/* Subscriber */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label className="form-label">Subscriber Name</label>
                <input className="form-input" value={subscriberName} onChange={e => setSubscriberName(e.target.value)} />
              </div>
              <div>
                <label className="form-label">Relationship</label>
                <select className="form-input" value={subscriberRelationship} onChange={e => setSubscriberRelationship(e.target.value)}>
                  {RELATIONSHIPS.map(r => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
                </select>
              </div>
              <div>
                <label className="form-label">Insurance Phone</label>
                <input className="form-input" value={insurancePhone} onChange={e => setInsurancePhone(e.target.value)} placeholder="+1-800-..." />
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem', paddingBottom: '0.25rem' }}>
                <input type="checkbox" id="isPrimary" checked={isPrimary} onChange={e => setIsPrimary(e.target.checked)} />
                <label htmlFor="isPrimary" style={{ fontWeight: 600, cursor: 'pointer' }}>Primary Plan</label>
              </div>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label className="form-label">Notes</label>
              <textarea className="form-input" rows={2} value={notes} onChange={e => setNotes(e.target.value)} />
            </div>

            <button type="submit" className="btn btn-primary" disabled={!region || !countryCode || !providerCode}>
              {editingPlan ? 'Update Plan' : 'Save Plan'}
            </button>
          </form>
        </div>
      )}

      {plans.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <Shield size={48} style={{ color: 'var(--color-text-secondary)', marginBottom: '1rem' }} />
          <h3>No Insurance Plans</h3>
          <p style={{ color: 'var(--color-text-secondary)' }}>Add your insurance plans to keep them handy. You can add multiple plans across different countries.</p>
        </div>
      ) : (
        <>
          {activePlans.length > 0 && (
            <div style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Shield size={18} /> Active Plans ({activePlans.length})
              </h3>
              <div style={{ display: 'grid', gap: '1rem' }}>
                {activePlans.map(plan => (
                  <InsuranceCard key={plan.id} plan={plan} onDelete={handleDelete} onSetPrimary={handleSetPrimary} onEdit={startEdit} />
                ))}
              </div>
            </div>
          )}
          {inactivePlans.length > 0 && (
            <div>
              <h3 style={{ marginBottom: '0.75rem', color: 'var(--color-text-secondary)' }}>Inactive Plans ({inactivePlans.length})</h3>
              <div style={{ display: 'grid', gap: '1rem' }}>
                {inactivePlans.map(plan => (
                  <InsuranceCard key={plan.id} plan={plan} onDelete={handleDelete} onSetPrimary={handleSetPrimary} onEdit={startEdit} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function InsuranceCard({ plan, onDelete, onSetPrimary, onEdit }) {
  const [expanded, setExpanded] = useState(false);

  const regionLabel = REGIONS.find(r => r.code === plan.region);

  return (
    <div className="card" style={{ padding: '1rem 1.25rem', opacity: plan.is_active ? 1 : 0.6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer', flex: 1 }} onClick={() => setExpanded(!expanded)}>
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <strong style={{ fontSize: '1.05rem' }}>{plan.provider_name}</strong>
              {plan.is_primary && (
                <span style={{ background: 'var(--color-warning)', color: '#fff', fontSize: '0.7rem', padding: '2px 8px', borderRadius: 10, fontWeight: 700 }}>
                  <Star size={10} style={{ marginRight: 2 }} /> PRIMARY
                </span>
              )}
              {!plan.is_active && (
                <span style={{ background: '#999', color: '#fff', fontSize: '0.7rem', padding: '2px 8px', borderRadius: 10 }}>INACTIVE</span>
              )}
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <span><Globe size={13} style={{ marginRight: 3 }} />{plan.country_name}</span>
              {plan.plan_name && <span>{plan.plan_name}</span>}
              {plan.plan_type && <span style={{ background: 'var(--color-bg-secondary)', padding: '1px 8px', borderRadius: 8, fontSize: '0.78rem' }}>{plan.plan_type}</span>}
              {plan.policy_number && <span>Policy: {plan.policy_number}</span>}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          {!plan.is_primary && plan.is_active && (
            <button className="btn" style={{ fontSize: '0.75rem', padding: '4px 10px' }} title="Set as Primary" onClick={() => onSetPrimary(plan.id)}>
              <Star size={14} /> Primary
            </button>
          )}
          <button className="btn" style={{ fontSize: '0.75rem', padding: '4px 8px' }} onClick={() => onEdit(plan)}><Edit3 size={14} /></button>
          <button className="btn" style={{ fontSize: '0.75rem', padding: '4px 8px', color: 'var(--color-danger)' }} onClick={() => onDelete(plan.id)}><Trash2 size={14} /></button>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.75rem', fontSize: '0.88rem' }}>
          <Detail label="Region" value={regionLabel ? `${regionLabel.emoji} ${regionLabel.name}` : plan.region} />
          <Detail label="Country" value={plan.country_name} />
          <Detail label="Provider" value={plan.provider_name} />
          <Detail label="Policy Number" value={plan.policy_number} />
          <Detail label="Group Number" value={plan.group_number} />
          <Detail label="Member ID" value={plan.member_id} />
          <Detail label="Plan Name" value={plan.plan_name} />
          <Detail label="Plan Type" value={plan.plan_type} />
          <Detail label="Coverage Start" value={plan.coverage_start} />
          <Detail label="Coverage End" value={plan.coverage_end} />
          <Detail label="Subscriber" value={plan.subscriber_name} />
          <Detail label="Relationship" value={plan.subscriber_relationship} />
          <Detail label="Phone" value={plan.insurance_phone} />
          {plan.notes && <div style={{ gridColumn: '1 / -1' }}><Detail label="Notes" value={plan.notes} /></div>}
        </div>
      )}
    </div>
  );
}

function Detail({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.78rem', marginBottom: 2 }}>{label}</div>
      <div style={{ fontWeight: 500 }}>{value}</div>
    </div>
  );
}
