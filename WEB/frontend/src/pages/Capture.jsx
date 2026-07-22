import { fmtDateTime, toDateTimeInput } from '../utils/datetime';
import { useEffect, useState } from 'react';
import api from '../services/api';
import BackButton from '../components/BackButton';

const categories = [
  { value: 'food', label: 'Food' },
  { value: 'elimination', label: 'Elimination' },
  { value: 'medication', label: 'Medication' },
  { value: 'injury', label: 'Injury' },
  { value: 'other', label: 'Other' },
];

export default function Capture() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    category: 'food',
    title: '',
    notes: '',
    captured_at: new Date().toISOString(),
    image_base64: '',
    content_type: '',
    file_name: '',
    file_size_bytes: 0,
    source: 'upload',
  });

  useEffect(() => {
    loadItems();
  }, []);

  async function loadItems() {
    const { data } = await api.get('/media/');
    setItems(data);
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result?.toString() || '';
      const [meta, base64] = result.split(',');
      const contentType = meta?.match(/data:(.*);base64/)
        ? meta.match(/data:(.*);base64/)[1]
        : file.type;

      setForm((prev) => ({
        ...prev,
        image_base64: base64 || '',
        content_type: contentType || file.type,
        file_name: file.name,
        file_size_bytes: file.size,
      }));
    };
    reader.readAsDataURL(file);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    await api.post('/media/', {
      ...form,
      captured_at: form.captured_at ? new Date(form.captured_at).toISOString() : null,
    });
    setForm({
      category: 'food',
      title: '',
      notes: '',
      captured_at: new Date().toISOString(),
      image_base64: '',
      content_type: '',
      file_name: '',
      file_size_bytes: 0,
      source: 'upload',
    });
    await loadItems();
    setLoading(false);
  }

  async function handleDelete(id) {
    await api.delete(`/media/${id}`);
    loadItems();
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Capture</h1>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Category</label>
              <select
                className="form-input"
                value={form.category}
                onChange={(e) => updateField('category', e.target.value)}
              >
                {categories.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Title</label>
              <input
                className="form-input"
                value={form.title}
                onChange={(e) => updateField('title', e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Captured At</label>
              <input
                className="form-input"
                type="datetime-local"
                value={toDateTimeInput(form.captured_at)}
                onChange={(e) => updateField('captured_at', e.target.value)}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Notes</label>
              <input
                className="form-input"
                value={form.notes}
                onChange={(e) => updateField('notes', e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Image</label>
              <input
                className="form-input"
                type="file"
                accept="image/*"
                capture="environment"
                onChange={handleFileChange}
              />
            </div>
          </div>

          <button className="btn btn-primary" type="submit" disabled={loading || !form.image_base64}>
            {loading ? 'Uploading...' : 'Save Capture'}
          </button>
        </form>
      </div>

      <div className="media-grid">
        {items.map((item) => (
          <div className="card media-card" key={item.id}>
            <img
              className="media-image"
              src={`data:${item.content_type || 'image/jpeg'};base64,${item.image_base64}`}
              alt={item.title || item.category}
            />
            <div className="media-meta">
              <div className="media-title">{item.title || item.category}</div>
              <div className="media-subtitle">{fmtDateTime(item.created_at)}</div>
            </div>
            <button className="btn btn-danger btn-sm" onClick={() => handleDelete(item.id)}>
              Delete
            </button>
          </div>
        ))}
        {items.length === 0 && (
          <div className="card" style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>
            No captures yet.
          </div>
        )}
      </div>
    </div>
  );
}
