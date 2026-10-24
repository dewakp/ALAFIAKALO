// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

/* The patient gives the amount; the app only offers what THEY said before.

   TASKS 25. An item logged with no amount is not counted. This asks for it,
   showing the amounts this patient has stated for that food earlier (their own
   history, never an estimate). Nothing is written until they press Save, and
   what is written is their amount — which then becomes history too. */

import { useState } from 'react';
import api from '../services/api';
import { t } from '../i18n';

function refusal(err) {
  const d = err?.response?.data?.detail;
  if (d && typeof d === 'object' && d.code) {
    if (d.code === 'not_a_measure' || d.code === 'empty') {
      return t('MissingAmounts.not_a_measure', { food: d.food_name });
    }
    return t('MissingAmounts.no_such_item', { food: d.food_name });
  }
  return t('MissingAmounts.failed');
}

export default function MissingAmounts({ logId, onSaved }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState(null);
  const [values, setValues] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setOpen(true);
    setError('');
    setItems(null);
    try {
      const { data } = await api.get(`/nutrition/${logId}/missing-amounts`);
      setItems(data.items || []);
    } catch {
      // An error is not an empty state: never say "nothing missing" here.
      setError(t('MissingAmounts.load_failed'));
    }
  };

  const save = async () => {
    const amounts = Object.fromEntries(
      Object.entries(values).map(([k, v]) => [k, (v || '').trim()]).filter(([, v]) => v));
    if (!Object.keys(amounts).length) return;
    setBusy(true);
    setError('');
    try {
      await api.post(`/nutrition/${logId}/amounts`, { amounts });
      setOpen(false);
      setValues({});
      onSaved?.();
    } catch (err) {
      setError(refusal(err));
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button type="button" className="btn btn-secondary btn-sm"
        style={{ marginTop: 4, fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif" }} onClick={start}>
        {t('MissingAmounts.add_amounts')}
      </button>
    );
  }

  return (
    // Drawn inside the calories cell, which is monospace and right-aligned:
    // set the page's own font and give it room, or it inherits both.
    <div data-testid="missing-amounts" style={{ marginTop: 6, padding: '.6rem', borderRadius: 6, textAlign: 'left',
      background: 'var(--color-bg-secondary, rgba(0,0,0,.03))', whiteSpace: 'normal', minWidth: '17rem',
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif", fontSize: '.8rem' }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{t('MissingAmounts.title')}</div>
      {items === null && !error && <div>{t('MissingAmounts.loading')}</div>}
      {items?.length === 0 && <div>{t('MissingAmounts.nothing')}</div>}
      {items?.map((it) => (
        <div key={it.food_name} style={{ marginBottom: 8 }}>
          <label style={{ display: 'block', fontWeight: 500 }} htmlFor={`amt-${logId}-${it.food_name}`}>
            {it.food_name}
          </label>
          {it.suggestions.length > 0 ? (
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', margin: '2px 0' }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>{t('MissingAmounts.your_earlier')}</span>
              {it.suggestions.map((s) => (
                <button key={s.amount} type="button" className="btn btn-secondary btn-sm"
                  onClick={() => setValues((v) => ({ ...v, [it.food_name]: s.amount }))}>
                  {t('MissingAmounts.times', { amount: s.amount, times: s.times })}
                </button>
              ))}
            </div>
          ) : (
            <div style={{ color: 'var(--color-text-secondary)' }}>{t('MissingAmounts.none_before')}</div>
          )}
          <input id={`amt-${logId}-${it.food_name}`} className="form-input" style={{ maxWidth: '14rem' }}
            placeholder={t('MissingAmounts.placeholder')} value={values[it.food_name] || ''}
            onChange={(e) => setValues((v) => ({ ...v, [it.food_name]: e.target.value }))} />
        </div>
      ))}
      {error && <div role="alert" style={{ color: '#b45309' }}>{error}</div>}
      <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
        <button type="button" className="btn btn-primary btn-sm" disabled={busy || !items?.length} onClick={save}>
          {t('MissingAmounts.save')}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(false)}>
          {t('MissingAmounts.cancel')}
        </button>
      </div>
    </div>
  );
}
