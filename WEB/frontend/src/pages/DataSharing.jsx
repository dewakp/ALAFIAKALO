import { useState, useEffect } from 'react';
import api from '../services/api';
import { Share2, Plus, Trash2, Mail, Check, X, Clock, Shield } from 'lucide-react';
import BackButton from '../components/BackButton';
import EHRPortals from '../components/EHRPortals';

export default function DataSharing() {
  const [activeTab, setActiveTab] = useState('grants');
  const [grants, setGrants] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [dataTypes, setDataTypes] = useState([]);
  const [showGrantForm, setShowGrantForm] = useState(false);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [grantForm, setGrantForm] = useState({ grantee_email: '', data_type: 'all', can_read: true, can_write: false, expires_at: '' });
  const [inviteForm, setInviteForm] = useState({ recipient_email: '', data_types: ['all'], message: '' });

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [g, inv, t] = await Promise.all([
        api.get('/data-sharing/grants'),
        api.get('/data-sharing/invitations'),
        api.get('/data-sharing/types'),
      ]);
      setGrants(g.data);
      setInvitations(inv.data);
      setDataTypes(t.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function createGrant(e) {
    e.preventDefault();
    try {
      const payload = { ...grantForm };
      if (!payload.expires_at) delete payload.expires_at;
      await api.post('/data-sharing/grants', payload);
      setShowGrantForm(false);
      setGrantForm({ grantee_email: '', data_type: 'all', can_read: true, can_write: false, expires_at: '' });
      loadAll();
    } catch (err) {
      alert('Error creating grant');
    }
  }

  async function deleteGrant(id) {
    if (!confirm('Revoke this data sharing grant?')) return;
    await api.delete(`/data-sharing/grants/${id}`);
    loadAll();
  }

  async function toggleGrant(id, isActive) {
    await api.patch(`/data-sharing/grants/${id}`, { is_active: !isActive });
    loadAll();
  }

  async function createInvitation(e) {
    e.preventDefault();
    try {
      await api.post('/data-sharing/invitations', inviteForm);
      setShowInviteForm(false);
      setInviteForm({ recipient_email: '', data_types: ['all'], message: '' });
      loadAll();
    } catch (err) {
      alert('Error creating invitation');
    }
  }

  async function respondToInvitation(id, action) {
    await api.post(`/data-sharing/invitations/${id}/${action}`);
    loadAll();
  }

  const tabs = [
    { key: 'grants', label: 'Active Grants', count: grants.length },
    { key: 'invitations', label: 'Invitations', count: invitations.length },
  ];

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Data Sharing</h1>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-primary" onClick={() => setShowGrantForm(!showGrantForm)}>
            <Plus size={16} /> Grant Access
          </button>
          <button className="btn btn-secondary" onClick={() => setShowInviteForm(!showInviteForm)}>
            <Mail size={16} /> Invite
          </button>
        </div>
      </div>

      {/* MyChart / patient-portal record connections */}
      <EHRPortals />

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        {tabs.map(t => (
          <button key={t.key} className={`btn ${activeTab === t.key ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab(t.key)}>
            {t.label} ({t.count})
          </button>
        ))}
      </div>

      {showGrantForm && (
        <div className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Grant Data Access</h3>
          <form onSubmit={createGrant}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Recipient Email *</label>
                <input className="form-input" type="email" required value={grantForm.grantee_email}
                  onChange={e => setGrantForm(p => ({ ...p, grantee_email: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">Data Type</label>
                <select className="form-select" value={grantForm.data_type}
                  onChange={e => setGrantForm(p => ({ ...p, data_type: e.target.value }))}>
                  {dataTypes.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={grantForm.can_read}
                    onChange={e => setGrantForm(p => ({ ...p, can_read: e.target.checked }))} /> Read Access
                </label>
              </div>
              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={grantForm.can_write}
                    onChange={e => setGrantForm(p => ({ ...p, can_write: e.target.checked }))} /> Write Access
                </label>
              </div>
              <div className="form-group">
                <label className="form-label">Expires (optional)</label>
                <input type="datetime-local" className="form-input" value={grantForm.expires_at}
                  onChange={e => setGrantForm(p => ({ ...p, expires_at: e.target.value }))} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
              <button type="submit" className="btn btn-primary">Create Grant</button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowGrantForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {showInviteForm && (
        <div className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Send Sharing Invitation</h3>
          <form onSubmit={createInvitation}>
            <div className="form-group">
              <label className="form-label">Recipient Email *</label>
              <input className="form-input" type="email" required value={inviteForm.recipient_email}
                onChange={e => setInviteForm(p => ({ ...p, recipient_email: e.target.value }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Data Types</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {dataTypes.map(t => (
                  <label key={t} style={{
                    display: 'flex', alignItems: 'center', gap: '0.25rem', padding: '4px 10px',
                    borderRadius: 8, background: inviteForm.data_types.includes(t) ? 'var(--color-primary-light)' : 'var(--color-bg)',
                    cursor: 'pointer', fontSize: '0.85rem',
                  }}>
                    <input type="checkbox" checked={inviteForm.data_types.includes(t)}
                      onChange={e => {
                        if (e.target.checked) setInviteForm(p => ({ ...p, data_types: [...p.data_types, t] }));
                        else setInviteForm(p => ({ ...p, data_types: p.data_types.filter(x => x !== t) }));
                      }} />
                    {t}
                  </label>
                ))}
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Message (optional)</label>
              <textarea className="form-input" rows={2} value={inviteForm.message}
                onChange={e => setInviteForm(p => ({ ...p, message: e.target.value }))} />
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
              <button type="submit" className="btn btn-primary">Send Invitation</button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowInviteForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {activeTab === 'grants' && (
        <div>
          {grants.length === 0 ? (
            <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
              <Shield size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
              <p>No active data sharing grants. Grant access to let others view your health data.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {grants.map(g => (
                <div key={g.id} className="card" style={{ padding: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <strong>{g.grantee_display_name || g.grantee_email || `User #${g.grantee_user_id}`}</strong>
                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem', fontSize: '0.85rem' }}>
                        <span style={{
                          padding: '1px 8px', borderRadius: 8, background: 'var(--color-primary-light)',
                          color: 'var(--color-primary-dark)', fontWeight: 600,
                        }}>{g.data_type}</span>
                        {g.can_read && <span style={{ color: 'var(--color-info)' }}>Read</span>}
                        {g.can_write && <span style={{ color: 'var(--color-warning)' }}>Write</span>}
                        {g.expires_at && <span style={{ color: 'var(--color-text-secondary)' }}>Expires: {new Date(g.expires_at).toLocaleDateString()}</span>}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button className={`btn btn-sm ${g.is_active ? 'btn-secondary' : 'btn-primary'}`}
                        onClick={() => toggleGrant(g.id, g.is_active)}>
                        {g.is_active ? 'Pause' : 'Resume'}
                      </button>
                      <button className="btn btn-sm" style={{ color: 'var(--color-danger)' }} onClick={() => deleteGrant(g.id)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'invitations' && (
        <div>
          {invitations.length === 0 ? (
            <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
              <Mail size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
              <p>No invitations.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {invitations.map(inv => {
                const statusColor = { pending: 'var(--color-warning)', accepted: 'var(--color-primary)', declined: 'var(--color-danger)', expired: 'var(--color-text-secondary)' };
                return (
                  <div key={inv.id} className="card" style={{ padding: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <strong>{inv.recipient_email || `User #${inv.recipient_user_id}`}</strong>
                          <span style={{
                            padding: '1px 8px', borderRadius: 8, fontSize: '0.75rem', fontWeight: 600,
                            background: statusColor[inv.status] + '20', color: statusColor[inv.status],
                          }}>{inv.status}</span>
                        </div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginTop: '0.25rem' }}>
                          Types: {inv.data_types?.join(', ')}
                          {inv.message && <span> · "{inv.message}"</span>}
                        </div>
                      </div>
                      {inv.status === 'pending' && (
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button className="btn btn-sm btn-primary" onClick={() => respondToInvitation(inv.id, 'accept')}>
                            <Check size={14} /> Accept
                          </button>
                          <button className="btn btn-sm" style={{ color: 'var(--color-danger)' }}
                            onClick={() => respondToInvitation(inv.id, 'decline')}>
                            <X size={14} /> Decline
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
