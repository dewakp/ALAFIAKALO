import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import api from '../services/api';
import BackButton from '../components/BackButton';

const PrivacySettings = () => {
  const { t } = useTranslation();
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [exportStatus, setExportStatus] = useState(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const response = await api.get('/privacy/settings');
      setSettings(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Failed to load privacy settings:', error);
      setMessage('Failed to load settings');
      setLoading(false);
    }
  };

  const updateSetting = async (key, value) => {
    try {
      const response = await api.put('/privacy/settings', { [key]: value });
      setSettings(response.data);
      setMessage('Settings updated successfully');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      console.error('Failed to update setting:', error);
      setMessage('Failed to update settings');
    }
  };

  const requestDataExport = async () => {
    setSaving(true);
    try {
      const response = await api.post('/privacy/export?export_format=json', {});
      setExportStatus(response.data);
      setMessage('Data export requested. Check back in a few minutes.');
      setTimeout(() => setMessage(''), 5000);
    } catch (error) {
      console.error('Failed to request export:', error);
      setMessage('Failed to request export');
    }
    setSaving(false);
  };

  const requestAccountDeletion = async () => {
    setSaving(true);
    try {
      await api.post('/privacy/delete-account', { reason: 'User requested deletion' });
      setMessage('Account deletion requested. You will be contacted for confirmation.');
      setShowDeleteConfirm(false);
      setTimeout(() => {
        localStorage.removeItem('token');
        window.location.href = '/';
      }, 3000);
    } catch (error) {
      console.error('Failed to request deletion:', error);
      setMessage('Failed to request deletion');
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="privacy-settings">
        <div className="loading">{t('common.loading')}</div>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="privacy-settings">
        <div className="error">{t('common.error')}</div>
      </div>
    );
  }

  return (
    <div className="privacy-settings">
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1>{t('privacy.title')}</h1>
        </div>
      </div>
      
      {message && (
        <div className={`message ${message.includes('Failed') ? 'error' : 'success'}`}>
          {message}
        </div>
      )}

      {/* Data Sharing Section */}
      <section className="settings-section">
        <h2>Data Sharing & Privacy</h2>
        
        <div className="setting-item">
          <label>
            <input
              type="checkbox"
              checked={settings.allow_anonymized_analytics}
              onChange={(e) => updateSetting('allow_anonymized_analytics', e.target.checked)}
            />
            <div>
              <strong>Anonymized Analytics</strong>
              <p>Help improve the platform by sharing anonymized usage data</p>
            </div>
          </label>
        </div>

        <div className="setting-item">
          <label>
            <input
              type="checkbox"
              checked={settings.allow_collective_insights}
              onChange={(e) => updateSetting('allow_collective_insights', e.target.checked)}
            />
            <div>
              <strong>{t('privacy.consent.data_sharing')}</strong>
              <p>Your data will be anonymized and used to improve AI recommendations for everyone</p>
            </div>
          </label>
        </div>

        <div className="setting-item">
          <label>
            <input
              type="checkbox"
              checked={settings.allow_research_participation}
              onChange={(e) => updateSetting('allow_research_participation', e.target.checked)}
            />
            <div>
              <strong>{t('privacy.consent.research')}</strong>
              <p>Participate in de-identified health research studies</p>
            </div>
          </label>
        </div>
      </section>

      {/* Communications Section */}
      <section className="settings-section">
        <h2>Communications</h2>
        
        <div className="setting-item">
          <label>
            <input
              type="checkbox"
              checked={settings.allow_marketing_emails}
              onChange={(e) => updateSetting('allow_marketing_emails', e.target.checked)}
            />
            <div>
              <strong>{t('privacy.consent.marketing')}</strong>
              <p>Receive promotional emails and special offers</p>
            </div>
          </label>
        </div>

        <div className="setting-item">
          <label>
            <input
              type="checkbox"
              checked={settings.allow_product_updates}
              onChange={(e) => updateSetting('allow_product_updates', e.target.checked)}
            />
            <div>
              <strong>Product Updates</strong>
              <p>Receive notifications about new features and updates</p>
            </div>
          </label>
        </div>

        <div className="setting-item">
          <label>
            <input
              type="checkbox"
              checked={settings.allow_health_reminders}
              onChange={(e) => updateSetting('allow_health_reminders', e.target.checked)}
            />
            <div>
              <strong>Health Reminders</strong>
              <p>Receive reminders for medications, appointments, and health tracking</p>
            </div>
          </label>
        </div>
      </section>

      {/* AI Settings Section */}
      <section className="settings-section">
        <h2>AI Preferences</h2>
        
        <div className="setting-item">
          <label>
            <input
              type="checkbox"
              checked={settings.ai_coaching_enabled}
              onChange={(e) => updateSetting('ai_coaching_enabled', e.target.checked)}
            />
            <div>
              <strong>{t('privacy.consent.ai_coaching')}</strong>
              <p>Receive personalized health recommendations from AI</p>
            </div>
          </label>
        </div>

        <div className="setting-item">
          <label>
            <input
              type="checkbox"
              checked={settings.ai_memory_enabled}
              onChange={(e) => updateSetting('ai_memory_enabled', e.target.checked)}
            />
            <div>
              <strong>AI Memory</strong>
              <p>Allow AI to learn from your patterns for better personalization</p>
            </div>
          </label>
        </div>

        <div className="setting-item">
          <label>
            <strong>AI Explanation Detail</strong>
            <select
              value={settings.ai_explainability_level || 'standard'}
              onChange={(e) => updateSetting('ai_explainability_level', e.target.value)}
              className="select-input"
            >
              <option value="minimal">Minimal - Just recommendations</option>
              <option value="standard">Standard - Brief explanations</option>
              <option value="detailed">Detailed - Full reasoning</option>
            </select>
          </label>
        </div>
      </section>

      {/* Security Section */}
      <section className="settings-section">
        <h2>Security</h2>
        
        <div className="setting-item">
          <label>
            <input
              type="checkbox"
              checked={settings.require_biometric_auth}
              onChange={(e) => updateSetting('require_biometric_auth', e.target.checked)}
            />
            <div>
              <strong>Biometric Authentication</strong>
              <p>Require fingerprint or face recognition on mobile devices</p>
            </div>
          </label>
        </div>

        <div className="setting-item">
          <label>
            <strong>Session Timeout</strong>
            <select
              value={settings.session_timeout_minutes}
              onChange={(e) => updateSetting('session_timeout_minutes', parseInt(e.target.value))}
              className="select-input"
            >
              <option value="15">15 minutes</option>
              <option value="30">30 minutes</option>
              <option value="60">1 hour</option>
              <option value="120">2 hours</option>
              <option value="1440">24 hours</option>
            </select>
          </label>
        </div>
      </section>

      {/* Compliance Info Section */}
      <section className="settings-section compliance-info">
        <h2>Compliance & Regulations</h2>
        <div className="info-grid">
          <div className="info-item">
            <strong>GDPR Status:</strong>
            <span className={settings.gdpr_applies ? 'applies' : 'not-applies'}>
              {settings.gdpr_applies ? '✓ Applies' : '○ Does not apply'}
            </span>
          </div>
          <div className="info-item">
            <strong>HIPAA Status:</strong>
            <span className={settings.hipaa_applies ? 'applies' : 'not-applies'}>
              {settings.hipaa_applies ? '✓ Applies' : '○ Does not apply'}
            </span>
          </div>
        </div>
        <p className="compliance-note">
          Your data is protected according to applicable healthcare privacy regulations.
        </p>
      </section>

      {/* Data Export Section */}
      <section className="settings-section danger-zone">
        <h2>Your Data Rights</h2>
        
        <div className="data-action">
          <div>
            <strong>{t('privacy.export_data')}</strong>
            <p>{t('privacy.export_data_description')}</p>
          </div>
          <button 
            onClick={requestDataExport} 
            disabled={saving}
            className="btn-secondary"
          >
            {saving ? 'Requesting...' : 'Export Data'}
          </button>
        </div>

        {exportStatus && (
          <div className="export-status">
            Status: {exportStatus.status}
            {exportStatus.download_url && (
              <a href={exportStatus.download_url} className="download-link">
                Download Now
              </a>
            )}
          </div>
        )}

        <div className="data-action delete-account">
          <div>
            <strong>{t('privacy.delete_account')}</strong>
            <p>{t('privacy.delete_account_warning')}</p>
          </div>
          <button 
            onClick={() => setShowDeleteConfirm(true)}
            className="btn-danger"
          >
            Delete Account
          </button>
        </div>
      </section>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="modal-overlay" onClick={() => setShowDeleteConfirm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>⚠️ Confirm Account Deletion</h2>
            <p>
              This action cannot be undone. All your health data, AI memories, and account 
              information will be permanently deleted.
            </p>
            <p>
              Are you absolutely sure you want to delete your account?
            </p>
            <div className="modal-actions">
              <button 
                onClick={() => setShowDeleteConfirm(false)}
                className="btn-secondary"
              >
                {t('common.cancel')}
              </button>
              <button 
                onClick={requestAccountDeletion}
                disabled={saving}
                className="btn-danger"
              >
                {saving ? 'Deleting...' : 'Yes, Delete My Account'}
              </button>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .privacy-settings {
          max-width: 800px;
          margin: 0 auto;
          padding: 20px;
        }

        .message {
          padding: 12px;
          border-radius: 8px;
          margin-bottom: 20px;
          text-align: center;
        }

        .message.success {
          background-color: #d4edda;
          color: #155724;
          border: 1px solid #c3e6cb;
        }

        .message.error {
          background-color: #f8d7da;
          color: #721c24;
          border: 1px solid #f5c6cb;
        }

        .settings-section {
          background: white;
          border-radius: 12px;
          padding: 24px;
          margin-bottom: 24px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .settings-section h2 {
          margin-top: 0;
          margin-bottom: 20px;
          color: #333;
        }

        .setting-item {
          padding: 16px 0;
          border-bottom: 1px solid #eee;
        }

        .setting-item:last-child {
          border-bottom: none;
        }

        .setting-item label {
          display: flex;
          align-items: flex-start;
          cursor: pointer;
          gap: 12px;
        }

        .setting-item input[type="checkbox"] {
          margin-top: 4px;
          width: 20px;
          height: 20px;
          cursor: pointer;
        }

        .setting-item strong {
          display: block;
          margin-bottom: 4px;
          color: #333;
        }

        .setting-item p {
          margin: 0;
          color: #666;
          font-size: 14px;
        }

        .select-input {
          width: 100%;
          padding: 8px 12px;
          margin-top: 8px;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 14px;
        }

        .compliance-info .info-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
          margin-bottom: 16px;
        }

        .info-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px;
          background: #f8f9fa;
          border-radius: 6px;
        }

        .applies {
          color: #28a745;
          font-weight: bold;
        }

        .not-applies {
          color: #6c757d;
        }

        .compliance-note {
          color: #666;
          font-size: 14px;
          font-style: italic;
        }

        .danger-zone {
          border: 2px solid #dc3545;
        }

        .data-action {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 0;
          border-bottom: 1px solid #eee;
        }

        .data-action:last-child {
          border-bottom: none;
        }

        .btn-secondary,
        .btn-danger {
          padding: 10px 24px;
          border: none;
          border-radius: 6px;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }

        .btn-secondary {
          background: #6c757d;
          color: white;
        }

        .btn-secondary:hover {
          background: #5a6268;
        }

        .btn-danger {
          background: #dc3545;
          color: white;
        }

        .btn-danger:hover {
          background: #c82333;
        }

        .btn-secondary:disabled,
        .btn-danger:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0,0,0,0.7);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }

        .modal {
          background: white;
          border-radius: 12px;
          padding: 32px;
          max-width: 500px;
          box-shadow: 0 4px 24px rgba(0,0,0,0.2);
        }

        .modal h2 {
          margin-top: 0;
          color: #dc3545;
        }

        .modal-actions {
          display: flex;
          gap: 12px;
          margin-top: 24px;
          justify-content: flex-end;
        }

        .export-status {
          margin-top: 12px;
          padding: 12px;
          background: #e7f3ff;
          border-radius: 6px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .download-link {
          color: #007bff;
          text-decoration: none;
          font-weight: 600;
        }

        .download-link:hover {
          text-decoration: underline;
        }
      `}</style>
    </div>
  );
};

export default PrivacySettings;
