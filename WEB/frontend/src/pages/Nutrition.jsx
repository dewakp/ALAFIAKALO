import { localToday, toDateInput } from '../utils/datetime';
import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import {
  Plus, Search, Apple, ChevronDown, ChevronRight,
  BarChart3, Utensils, X, Loader2, Info, Calendar, Zap, Camera, Image, Sparkles, Link,
} from 'lucide-react';
import BackButton from '../components/BackButton';
import { usePromptPrefill } from '../hooks/usePromptPrefill';

/* ─── tiny helpers ─── */
const today = () => localToday();
const pct = (v, rda) => (rda ? Math.min(Math.round((v / rda) * 100), 999) : null);
const colorForPct = (p) => {
  if (p == null) return 'var(--color-text-tertiary)';
  if (p < 25) return '#ef4444';
  if (p < 75) return '#f59e0b';
  return '#22c55e';
};

/* Nutrient category display order */
const CAT_ORDER = [
  'Energy', 'Macronutrients', 'Fats', 'Minerals', 'Vitamins',
  'Other', 'Amino Acids', 'Fatty Acids', 'Sterols', 'Carotenoids', 'Sugars',
];

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
export default function Nutrition() {
  /* ── state ── */
  const [tab, setTab] = useState('log');           // log | summary
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  // Date-range filter for food log
  const sevenDaysAgo = () => { const d = new Date(); d.setDate(d.getDate() - 6); return toDateInput(d); };
  const [filterStart, setFilterStart] = useState(sevenDaysAgo);
  const [filterEnd, setFilterEnd] = useState(today);

  // Form
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editingId, setEditingId] = useState(null);       // null = adding; id = editing that entry
  const [editOriginalFood, setEditOriginalFood] = useState('');
  const [form, setForm] = useState({
    log_date: today(), meal_type: 'breakfast', food_name: '',
    serving_size: '', fdc_id: null, notes: '',
    start_time: '', end_time: '', pre_meal_weight_kg: '', post_meal_weight_kg: '',
    recipe_url: '',
  });

  // Prompt Hub hand-off: open the add-food form pre-filled from the prompt.
  usePromptPrefill((prefill) => {
    const items = Array.isArray(prefill.items) ? prefill.items : null;
    const foodName = items
      ? items.map((i) => (typeof i === 'string' ? i : i.name || i.food_name)).filter(Boolean).join(', ')
      : (prefill.food || prefill.text || '');
    setForm((f) => ({
      ...f,
      food_name: foodName || f.food_name,
      notes: prefill.notes || f.notes,
    }));
    setTab('log');
    setShowForm(true);
  });

  // Image analysis
  const [imageFiles, setImageFiles] = useState([]);
  const [imageAnalysisResult, setImageAnalysisResult] = useState('');
  const [isAnalyzingImages, setIsAnalyzingImages] = useState(false);
  const imageInputRef = useRef(null);
  const formRef = useRef(null);   // edit/add form card — for scroll-into-view on Edit
  const [searchParams, setSearchParams] = useSearchParams();

  // USDA search
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const searchTimer = useRef(null);
  const nlmTimer = useRef(null);   // debounce NLM auto-estimation

  // Nutrient estimation preview (before save)
  const [estimating, setEstimating] = useState(false);
  const [estimatePreview, setEstimatePreview] = useState(null);
  const [estimateError, setEstimateError] = useState('');

  // Recipe-URL analysis (third meal input: URL / description / photo)
  const [analyzingRecipe, setAnalyzingRecipe] = useState(false);
  const [recipeInfo, setRecipeInfo] = useState('');

  // Nutrient detail panel (for a single food)
  const [selectedFood, setSelectedFood] = useState(null);
  const [foodDetail, setFoodDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Daily summary
  const [summaryDate, setSummaryDate] = useState(today());
  const [summary, setSummary] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(false);

  // Expanded categories
  const [expandedCats, setExpandedCats] = useState(new Set(['Energy', 'Macronutrients', 'Vitamins', 'Minerals']));

  /* ── data loading ── */
  const loadLogs = useCallback(async (start, end) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (start) params.set('start_date', start);
      if (end)   params.set('end_date', end);
      const qs = params.toString();
      const { data } = await api.get(`/nutrition/${qs ? '?' + qs : ''}`);
      setLogs(data);
    } catch {} finally { setLoading(false); }
  }, []);

  const loadSummary = useCallback(async (d) => {
    setLoadingSummary(true);
    try {
      const { data } = await api.get(`/nutrition/daily-summary?date=${d}`);
      setSummary(data);
    } catch { setSummary(null); } finally { setLoadingSummary(false); }
  }, []);

  useEffect(() => { loadLogs(filterStart, filterEnd); }, [loadLogs, filterStart, filterEnd]);
  useEffect(() => { if (tab === 'summary') loadSummary(summaryDate); }, [tab, summaryDate, loadSummary]);

  /* ── USDA search (debounced) ── */
  const handleSearchInput = (val) => {
    setSearchQuery(val);
    clearTimeout(searchTimer.current);
    if (val.length < 2) { setSearchResults([]); return; }
    searchTimer.current = setTimeout(async () => {
      setSearching(true);
      try {
        const { data } = await api.get(`/nutrition/food-search?q=${encodeURIComponent(val)}&page_size=15`);
        setSearchResults(data);
      } catch {} finally { setSearching(false); }
    }, 400);
  };

  const selectUSDAFood = (food) => {
    setForm({ ...form, food_name: food.description, fdc_id: food.fdc_id,
      serving_size: food.serving_size ? `${food.serving_size} ${food.serving_size_unit || 'g'}` : '100 g',
    });
    setShowSearch(false);
    setSearchResults([]);
    setSearchQuery('');
  };

  /* ── food detail ── */
  const openFoodDetail = async (fdcId, name) => {
    setSelectedFood(name);
    setLoadingDetail(true);
    try {
      const { data } = await api.get(`/nutrition/food/${fdcId}`);
      setFoodDetail(data);
    } catch { setFoodDetail(null); } finally { setLoadingDetail(false); }
  };

  /* Analyze a recipe link: parse the page's structured recipe, price the
     ingredients, prefill the entry with per-serving nutrition. Published
     nutrition is learned server-side under the dish name. */
  const analyzeRecipeUrl = async () => {
    const url = form.recipe_url.trim();
    if (!url) return;
    setAnalyzingRecipe(true); setRecipeInfo('');
    try {
      const { data } = await api.post('/nutrition/recipe-analyze', { url }, { timeout: 120000 });
      setForm((prev) => ({
        ...prev,
        food_name: prev.food_name.trim() || data.name,
        serving_size: prev.serving_size?.trim() || `1 serving (of ${data.servings})`,
      }));
      setEstimatePreview({
        source: data.source === 'published' ? 'recipe (published)' : 'recipe (estimated)',
        nutrients: data.per_serving,
        serving_size: `1 serving (of ${data.servings})`,
      });
      setRecipeInfo(
        `${data.name} — ${data.ingredients.length} ingredients, ${data.servings} servings` +
        (data.learned ? '. Published nutrition learned for this dish.' : '')
      );
    } catch (err) {
      setRecipeInfo(apiErrorMessage(err, 'Could not analyze that recipe link'));
    } finally { setAnalyzingRecipe(false); }
  };

  const estimateBeforeSave = async ({ silent = false } = {}) => {
    const foodName = form.food_name.trim();
    if (!foodName || form.fdc_id) return;

    setEstimating(true);
    if (!silent) setEstimateError('');

    try {
      const payload = { food_name: foodName };
      if (form.serving_size?.trim()) payload.serving_size = form.serving_size.trim();

      const { data } = await api.post('/nutrition/estimate-nutrients', payload);

      if (!data?.source) {
        setEstimatePreview(null);
        if (!silent) {
          setEstimateError('No nutrient estimate available yet. You can still save this entry.');
        }
        return;
      }

      setEstimatePreview(data);
      setEstimateError('');
    } catch {
      if (!silent) {
        setEstimateError('Failed to fetch nutrient suggestion. Please try again.');
      }
    } finally {
      setEstimating(false);
    }
  };

  /* ── CRUD ── */
  const resetForm = () => {
    setShowForm(false);
    setEditingId(null);
    setEditOriginalFood('');
    setForm({ log_date: today(), meal_type: 'breakfast', food_name: '', serving_size: '', fdc_id: null, notes: '',
      start_time: '', end_time: '', pre_meal_weight_kg: '', post_meal_weight_kg: '', recipe_url: '' });
    setEstimatePreview(null);
    setImageFiles([]);
    setImageAnalysisResult('');
    setEstimateError('');
  };

  // Open the form pre-filled to edit an existing entry.
  const startEdit = (log) => {
    setForm({
      log_date: log.log_date,
      meal_type: log.meal_type || 'breakfast',
      food_name: log.food_name || '',
      serving_size: log.serving_size || '',
      fdc_id: log.fdc_id || null,
      notes: log.notes || '',
      start_time: log.start_time ? log.start_time.slice(0, 5) : '',
      end_time: log.end_time ? log.end_time.slice(0, 5) : '',
      pre_meal_weight_kg: log.pre_meal_weight_kg ?? '',
      post_meal_weight_kg: log.post_meal_weight_kg ?? '',
      recipe_url: log.recipe_url || '',
    });
    setEditOriginalFood(log.food_name || '');
    setEditingId(log.id);
    setEstimatePreview(null);
    setEstimateError('');
    setTab('log');
    setShowForm(true);
    // Scroll the form into view. scrollIntoView (not window.scrollTo) works even
    // when an inner <main> is the scroll container, not the window. Delayed so the
    // form has rendered after setShowForm.
    setTimeout(() => formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60);
  };

  // Deep-link from Meals Diary: /nutrition?edit=<id> opens that entry in the edit form.
  useEffect(() => {
    const editId = searchParams.get('edit');
    if (!editId) return;
    (async () => {
      try {
        const { data } = await api.get(`/nutrition/${editId}`);
        startEdit(data);
      } catch { /* entry not found — ignore */ }
      setSearchParams({}, { replace: true });
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const payload = { ...form };
      for (const k of ['serving_size', 'notes', 'recipe_url', 'start_time', 'end_time',
                       'pre_meal_weight_kg', 'post_meal_weight_kg']) {
        if (!payload[k]) delete payload[k];
      }

      if (editingId) {
        // If the description changed, re-estimate so calories/macros stay accurate.
        // Time-boxed so a slow AI fallback can't hang the save — we still patch the
        // user's field edits if re-estimation is slow/unavailable.
        if (form.food_name && form.food_name.trim() !== editOriginalFood.trim()) {
          try {
            const { data } = await api.post('/nutrition/estimate-meal',
              { description: form.food_name }, { timeout: 25000 });
            Object.assign(payload, data.aggregate_nutrients || {});
            if (data.total_weight_g) payload.serving_size = `composite meal (${Math.round(data.total_weight_g)} g total)`;
          } catch { /* keep existing values if estimation is slow/fails */ }
        }
        delete payload.fdc_id;       // not part of the update schema
        await api.patch(`/nutrition/${editingId}`, payload);  // log_date now editable
      } else {
        await api.post('/nutrition/', payload);
      }

      resetForm();
      loadLogs(filterStart, filterEnd);
      if (tab === 'summary') loadSummary(summaryDate);
    } catch (err) {
      alert(`Could not save: ${err?.response?.data?.detail || err.message || 'unknown error'}`);
    } finally {
      setSubmitting(false);
    }
  };

  const toggleCat = (cat) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      next.has(cat) ? next.delete(cat) : next.add(cat);
      return next;
    });
  };

  /* ━━━ Nutrient Breakdown Component ━━━ */
  const NutrientBreakdown = ({ nutrients, title }) => {
    if (!nutrients || nutrients.length === 0) return null;
    const grouped = {};
    nutrients.forEach((n) => {
      if (!grouped[n.category]) grouped[n.category] = [];
      grouped[n.category].push(n);
    });
    return (
      <div style={{ marginTop: '1rem' }}>
        {title && <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '.75rem' }}>{title}</h3>}
        {CAT_ORDER.filter((c) => grouped[c]).map((cat) => (
          <div key={cat} style={{ marginBottom: '.5rem' }}>
            <button onClick={() => toggleCat(cat)}
              style={{ display: 'flex', alignItems: 'center', gap: '.35rem', background: 'none', border: 'none',
                cursor: 'pointer', fontWeight: 600, fontSize: '.875rem', color: 'var(--color-text-primary)',
                padding: '.35rem 0', width: '100%', textAlign: 'left' }}>
              {expandedCats.has(cat) ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}
              {cat} <span style={{ color: 'var(--color-text-tertiary)', fontWeight: 400 }}>({grouped[cat].length})</span>
            </button>
            {expandedCats.has(cat) && (
              <div style={{ display: 'grid', gap: '.35rem', paddingLeft: '1rem' }}>
                {grouped[cat].map((n) => {
                  const p = n.percent_dv;
                  return (
                    <div key={n.key} style={{ display: 'grid', gridTemplateColumns: '1fr 80px 50px 100px', alignItems: 'center', fontSize: '.8rem', gap: '.5rem' }}>
                      <span style={{ color: 'var(--color-text-secondary)' }}>{n.name}</span>
                      <span style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                        {n.value != null ? Number(n.value).toFixed(1) : '—'} {n.unit}
                      </span>
                      <span style={{ textAlign: 'right', fontFamily: 'monospace', color: colorForPct(p), fontWeight: p != null ? 600 : 400 }}>
                        {p != null ? `${p}%` : '—'}
                      </span>
                      {p != null ? (
                        <div style={{ background: 'var(--color-bg-secondary)', borderRadius: 4, height: 8, overflow: 'hidden' }}>
                          <div style={{ width: `${Math.min(p, 100)}%`, height: '100%', background: colorForPct(p), borderRadius: 4, transition: 'width .3s' }}/>
                        </div>
                      ) : <div/>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  /* ━━━━━━━━━━━━━━━━ RENDER ━━━━━━━━━━━━━━━━ */
  return (
    <div>
      {/* ── Header ── */}
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Nutrition</h1>
        </div>
        <div style={{ display: 'flex', gap: '.5rem' }}>
          <button className={`btn ${tab === 'log' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('log')}>
            <Utensils size={16}/> Food Log
          </button>
          <button className={`btn ${tab === 'summary' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('summary')}>
            <BarChart3 size={16}/> Daily Summary
          </button>
          {tab === 'log' && (
            <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
              <Plus size={18}/> Add Entry
            </button>
          )}
        </div>
      </div>

      {/* ═══════════ ADD / EDIT FORM ═══════════ */}
      {showForm && tab === 'log' && (
        <div ref={formRef} className="card" style={{ marginBottom: '1.5rem', position: 'relative' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ margin: 0, fontSize: '1rem' }}>{editingId ? '✏️ Edit Meal Entry' : '⊕ Log New Meal'}</h3>
            <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center' }}>
              {/* NLM always-active indicator */}
              <span style={{ display: 'flex', alignItems: 'center', gap: '.3rem', fontSize: '.72rem',
                color: estimating ? '#f59e0b' : '#22c55e',
                background: estimating ? 'rgba(245,158,11,.1)' : 'rgba(34,197,94,.1)',
                border: `1px solid ${estimating ? 'rgba(245,158,11,.3)' : 'rgba(34,197,94,.3)'}`,
                borderRadius: 12, padding: '.2rem .6rem', fontWeight: 600 }}>
                {estimating
                  ? <><Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }}/> NLM analyzing…</>
                  : <><Zap size={11}/> NLM active</>}
              </span>
              <button className="btn btn-secondary btn-sm" type="button"
                onClick={() => { setShowSearch(!showSearch); setSearchResults([]); setSearchQuery(''); }}>
                <Search size={14}/> Search USDA Database
              </button>
            </div>
          </div>

          {/* USDA search dropdown */}
          {showSearch && (
            <div style={{ marginBottom: '1rem', position: 'relative' }}>
              <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center' }}>
                <input className="form-input" placeholder="Search foods (e.g. banana, chicken breast)..."
                  value={searchQuery} onChange={(e) => handleSearchInput(e.target.value)} autoFocus
                  style={{ flex: 1 }}/>
                {searching && <Loader2 size={18} className="spin" style={{ animation: 'spin 1s linear infinite' }}/>}
              </div>
              {searchResults.length > 0 && (
                <div style={{ border: '1px solid var(--color-border)', borderRadius: 8, maxHeight: 280, overflowY: 'auto',
                  marginTop: '.5rem', background: 'var(--color-bg-primary)' }}>
                  {searchResults.map((f) => (
                    <div key={f.fdc_id} onClick={() => selectUSDAFood(f)}
                      style={{ padding: '.6rem .8rem', cursor: 'pointer', borderBottom: '1px solid var(--color-border)',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '.85rem' }}
                      onMouseOver={(e) => e.currentTarget.style.background = 'var(--color-bg-secondary)'}
                      onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}>
                      <div>
                        <div style={{ fontWeight: 500 }}>{f.description}</div>
                        <div style={{ fontSize: '.75rem', color: 'var(--color-text-tertiary)' }}>
                          {f.data_type}{f.brand_owner ? ` · ${f.brand_owner}` : ''} · {Object.keys(f.nutrients).length} nutrients
                        </div>
                      </div>
                      <div style={{ textAlign: 'right', fontSize: '.75rem', color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                        {f.nutrients.calories ? `${Math.round(f.nutrients.calories)} kcal` : ''}
                        {f.nutrients.protein_g ? ` · ${f.nutrients.protein_g.toFixed(1)}g P` : ''}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Image Analysis Section */}
          <div style={{ border: '1px solid var(--color-border)', borderRadius: 8, padding: '.75rem', marginBottom: '1rem' }}>
            <div style={{ fontSize: '.8rem', fontWeight: 600, marginBottom: '.5rem', display: 'flex', alignItems: 'center', gap: '.4rem' }}>
              <Image size={14}/> Identify Food from Image (Optional – Max 3 images)
            </div>
            <div style={{ fontSize: '.72rem', color: 'var(--color-text-tertiary)', marginBottom: '.5rem' }}>
              Upload image(s) or take a photo for Alafia analysis.
            </div>
            <input ref={imageInputRef} type="file" accept="image/*" multiple style={{ display: 'none' }}
              onChange={(e) => {
                const added = Array.from(e.target.files || []).slice(0, 3 - imageFiles.length);
                setImageFiles((prev) => [...prev, ...added].slice(0, 3));
                e.target.value = '';
              }}/>
            <div style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', marginBottom: '.5rem' }}>
              <button type="button" className="btn btn-secondary btn-sm"
                onClick={() => imageInputRef.current?.click()}
                disabled={imageFiles.length >= 3}>
                Choose Files
              </button>
              {imageFiles.length === 0 && <span style={{ fontSize: '.8rem', color: 'var(--color-text-tertiary)', alignSelf: 'center' }}>no files selected</span>}
              {imageFiles.map((f, i) => (
                <span key={i} style={{ display: 'flex', alignItems: 'center', gap: '.3rem', fontSize: '.75rem',
                  background: 'var(--color-bg-secondary)', borderRadius: 4, padding: '.2rem .5rem' }}>
                  {f.name}
                  <button type="button" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--color-text-tertiary)' }}
                    onClick={() => setImageFiles((prev) => prev.filter((_, j) => j !== i))}>
                    <X size={12}/>
                  </button>
                </span>
              ))}
            </div>
            <button type="button" className="btn btn-primary" style={{ width: '100%' }}
              disabled={imageFiles.length === 0 || isAnalyzingImages}
              onClick={() => {
                // TODO(alafia-model): replace with ALAFIAModel.infer(.vision, images) — Phase 5
                setIsAnalyzingImages(true);
                setTimeout(() => {
                  setIsAnalyzingImages(false);
                  setImageAnalysisResult('Image analysis coming soon (ALAFIAModel Phase 5)');
                }, 800);
              }}>
              {isAnalyzingImages ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }}/> Analysing…</> : <><Sparkles size={14}/> Analyse Image(s) with Alafia</>}
            </button>
            {imageAnalysisResult && (
              <div style={{ marginTop: '.5rem', fontSize: '.78rem', color: 'var(--color-text-secondary)' }}>{imageAnalysisResult}</div>
            )}
          </div>

          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Date</label>
                <input className="form-input" type="date" value={form.log_date}
                  onChange={(e) => setForm({ ...form, log_date: e.target.value })} required/>
              </div>
              <div className="form-group">
                <label className="form-label">Meal</label>
                <select className="form-input" value={form.meal_type}
                  onChange={(e) => setForm({ ...form, meal_type: e.target.value })}>
                  <option value="breakfast">Breakfast</option>
                  <option value="lunch">Lunch</option>
                  <option value="dinner">Dinner</option>
                  <option value="snack">Snack</option>
                </select>
              </div>
              <div className="form-group" style={{ flex: 2 }}>
                <label className="form-label">Food {form.fdc_id && <span style={{ color: '#22c55e', fontSize: '.7rem' }}>✓ USDA linked</span>}</label>
                <input className="form-input" value={form.food_name}
                  onChange={(e) => {
                    const val = e.target.value;
                    setForm({ ...form, food_name: val, fdc_id: null });
                    setEstimatePreview(null);
                    setEstimateError('');
                    // Auto-trigger NLM with debounce (always active)
                    // TODO(alafia-model): replace with ALAFIAModel.infer('nlm', val) — Phase 1
                    clearTimeout(nlmTimer.current);
                    if (val.trim().length >= 3) {
                      nlmTimer.current = setTimeout(() => estimateBeforeSave({ silent: true }), 700);
                    }
                  }}
                  required/>
              </div>
              <div className="form-group">
                <label className="form-label">Serving Size</label>
                <input className="form-input" value={form.serving_size} placeholder="e.g. 100 g"
                  onChange={(e) => setForm({ ...form, serving_size: e.target.value })}/>
              </div>
            </div>
            {form.fdc_id && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', padding: '.5rem .75rem',
                background: 'rgba(34,197,94,.08)', borderRadius: 8, marginBottom: '.75rem', fontSize: '.8rem' }}>
                <Zap size={14} style={{ color: '#22c55e' }}/>
                <span>Nutrients will be auto-populated from the USDA database when saved.</span>
                <button type="button" style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-tertiary)' }}
                  onClick={() => openFoodDetail(form.fdc_id, form.food_name)}>
                  <Info size={14}/> Preview nutrients
                </button>
              </div>
            )}
            {estimatePreview && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '.5rem', padding: '.6rem .75rem',
                background: 'rgba(59,130,246,.08)', borderRadius: 8, marginBottom: '.75rem', fontSize: '.8rem', border: '1px solid rgba(59,130,246,.2)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', flexWrap: 'wrap' }}>
                  <Info size={14} style={{ color: '#3b82f6' }}/>
                  <strong style={{ color: '#1d4ed8' }}>Pre-save nutrient suggestion</strong>
                  <span style={{ color: 'var(--color-text-secondary)' }}>
                    Source: {estimatePreview.source?.toUpperCase() || 'UNKNOWN'}
                    {estimatePreview.confidence != null ? ` · ${Math.round(estimatePreview.confidence * 100)}% confidence` : ''}
                    {estimatePreview.cached ? ' · cached' : ''}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: '.75rem', flexWrap: 'wrap', color: 'var(--color-text-secondary)' }}>
                  <span>Calories: <strong>{estimatePreview.nutrients?.calories ?? '—'}</strong></span>
                  <span>Protein: <strong>{estimatePreview.nutrients?.protein_g ?? '—'}g</strong></span>
                  <span>Carbs: <strong>{estimatePreview.nutrients?.carbs_g ?? '—'}g</strong></span>
                  <span>Fat: <strong>{estimatePreview.nutrients?.fat_g ?? '—'}g</strong></span>
                </div>
                {(estimatePreview.fdc_id || estimatePreview.serving_size) && (
                  <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => {
                      setForm((prev) => ({
                        ...prev,
                        fdc_id: estimatePreview.fdc_id || prev.fdc_id,
                        serving_size: prev.serving_size || estimatePreview.serving_size || '',
                      }));
                    }}>
                      Apply suggestion
                    </button>
                    {estimatePreview.fdc_id && <span style={{ color: 'var(--color-text-secondary)' }}>USDA FDC linked from suggestion.</span>}
                  </div>
                )}
              </div>
            )}
            {estimateError && (
              <div style={{ marginBottom: '.75rem', color: '#dc2626', fontSize: '.8rem' }}>{estimateError}</div>
            )}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Start Time</label>
                <input className="form-input" type="time" value={form.start_time}
                  onChange={(e) => setForm({ ...form, start_time: e.target.value })}/>
              </div>
              <div className="form-group">
                <label className="form-label">End Time</label>
                <input className="form-input" type="time" value={form.end_time}
                  onChange={(e) => setForm({ ...form, end_time: e.target.value })}/>
              </div>
              <div className="form-group">
                <label className="form-label">Pre-meal Weight (kg)</label>
                <input className="form-input" type="number" step="0.1" placeholder="e.g. 72.5"
                  value={form.pre_meal_weight_kg}
                  onChange={(e) => setForm({ ...form, pre_meal_weight_kg: e.target.value })}/>
              </div>
              <div className="form-group">
                <label className="form-label">Post-meal Weight (kg)</label>
                <input className="form-input" type="number" step="0.1" placeholder="e.g. 73.2"
                  value={form.post_meal_weight_kg}
                  onChange={(e) => setForm({ ...form, post_meal_weight_kg: e.target.value })}/>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label"><Link size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/>Recipe URL (Optional)</label>
              <div style={{ display: 'flex', gap: '.5rem' }}>
                <input className="form-input" type="url" placeholder="https://example.com/recipe" style={{ flex: 1 }}
                  value={form.recipe_url}
                  onChange={(e) => setForm({ ...form, recipe_url: e.target.value })}/>
                <button type="button" className="btn btn-secondary" disabled={!form.recipe_url.trim() || analyzingRecipe}
                  onClick={analyzeRecipeUrl}>
                  {analyzingRecipe ? 'Analyzing…' : 'Analyze'}
                </button>
              </div>
              {recipeInfo && (
                <p style={{ marginTop: 6, fontSize: '.78rem', color: 'var(--color-text-secondary)' }}>{recipeInfo}</p>
              )}
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <input className="form-input" value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}/>
            </div>
            <div style={{ display: 'flex', gap: '.5rem' }}>
              <button className="btn btn-primary" type="submit" disabled={submitting}>
                {submitting ? 'Saving…' : (editingId ? 'Update Entry' : 'Save')}
              </button>
              <button className="btn btn-secondary" type="button" onClick={resetForm} disabled={submitting}>{editingId ? 'Cancel Edit' : 'Cancel'}</button>
            </div>
            <div style={{ marginTop: '.5rem', color: 'var(--color-text-secondary)', fontSize: '.78rem' }}>
              Nutrient values shown here are suggestions. Final nutrient data is persisted server-side when you save.
            </div>
          </form>
        </div>
      )}

      {/* ═══════════ FOOD LOG TAB ═══════════ */}
      {tab === 'log' && (
        <div className="card">
          {/* ── Date-range filter bar ── */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem', flexWrap: 'wrap', marginBottom: '1rem',
            paddingBottom: '.75rem', borderBottom: '1px solid var(--color-border)' }}>
            <Calendar size={15} style={{ color: 'var(--color-text-secondary)', flexShrink: 0 }}/>
            <input type="date" className="form-input" value={filterStart}
              onChange={(e) => setFilterStart(e.target.value)}
              style={{ maxWidth: 148, padding: '.3rem .5rem', fontSize: '.82rem' }}/>
            <span style={{ color: 'var(--color-text-tertiary)', fontSize: '.82rem' }}>to</span>
            <input type="date" className="form-input" value={filterEnd}
              onChange={(e) => setFilterEnd(e.target.value)}
              style={{ maxWidth: 148, padding: '.3rem .5rem', fontSize: '.82rem' }}/>
            <div style={{ display: 'flex', gap: '.35rem' }}>
              {[
                { label: 'Today',  fn: () => { setFilterStart(today()); setFilterEnd(today()); } },
                { label: '7 days', fn: () => { const d = new Date(); d.setDate(d.getDate()-6); setFilterStart(toDateInput(d)); setFilterEnd(today()); } },
                { label: '30 days',fn: () => { const d = new Date(); d.setDate(d.getDate()-29); setFilterStart(toDateInput(d)); setFilterEnd(today()); } },
                { label: 'All',    fn: () => { setFilterStart(''); setFilterEnd(''); } },
              ].map(({ label, fn }) => (
                <button key={label} className="btn btn-secondary btn-sm" type="button" onClick={fn}
                  style={{ padding: '.25rem .6rem', fontSize: '.75rem' }}>{label}</button>
              ))}
            </div>
            <span style={{ marginLeft: 'auto', fontSize: '.8rem', color: 'var(--color-text-tertiary)' }}>
              {logs.length} {logs.length === 1 ? 'entry' : 'entries'}
            </span>
          </div>

          <div style={{ marginBottom: '.75rem', color: 'var(--color-text-secondary)', fontSize: '.8rem' }}>
            Entries are editable but cannot be deleted.
          </div>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-tertiary)' }}>Loading...</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Meal</th>
                  <th>Food</th>
                  <th>Serving</th>
                  <th>Time</th>
                  <th style={{ textAlign: 'right' }}>Calories</th>
                  <th style={{ textAlign: 'right' }}>Protein</th>
                  <th style={{ textAlign: 'right' }}>Carbs</th>
                  <th style={{ textAlign: 'right' }}>Fat</th>
                  <th style={{ textAlign: 'right' }}>Pre kg</th>
                  <th style={{ textAlign: 'right' }}>Post kg</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td>{log.log_date}</td>
                    <td style={{ textTransform: 'capitalize' }}>{log.meal_type}</td>
                    <td>
                      <span style={{ fontWeight: 500 }}>{log.food_name}</span>
                      {log.fdc_id && (
                        <button onClick={() => openFoodDetail(log.fdc_id, log.food_name)}
                          style={{ marginLeft: '.35rem', background: 'none', border: 'none', cursor: 'pointer', color: '#3b82f6', fontSize: '.7rem', fontWeight: 600 }}>
                          USDA ↗
                        </button>
                      )}
                    </td>
                    <td style={{ fontSize: '.8rem', color: 'var(--color-text-secondary)' }}>{log.serving_size || '—'}</td>
                    <td style={{ fontSize: '.75rem', color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                      {log.start_time ? log.start_time.slice(0, 5) : ''}
                      {log.start_time && log.end_time ? '–' : ''}
                      {log.end_time ? log.end_time.slice(0, 5) : ''}
                      {!log.start_time && !log.end_time ? '—' : ''}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{log.calories != null ? Math.round(log.calories) : '—'}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{log.protein_g != null ? `${log.protein_g.toFixed(1)}g` : '—'}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{log.carbs_g != null ? `${log.carbs_g.toFixed(1)}g` : '—'}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{log.fat_g != null ? `${log.fat_g.toFixed(1)}g` : '—'}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', fontSize: '.8rem' }}>{log.pre_meal_weight_kg != null ? `${log.pre_meal_weight_kg}` : '—'}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', fontSize: '.8rem' }}>{log.post_meal_weight_kg != null ? `${log.post_meal_weight_kg}` : '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn-secondary btn-sm" onClick={() => startEdit(log)}>Edit</button>
                    </td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr><td colSpan={9} style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: '2rem' }}>
                    No entries yet — search the USDA database to add foods with full nutrient data
                  </td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ═══════════ DAILY SUMMARY TAB ═══════════ */}
      {tab === 'summary' && (
        <div>
          {/* Date picker */}
          <div className="card" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <Calendar size={18}/>
            <input type="date" className="form-input" value={summaryDate}
              onChange={(e) => setSummaryDate(e.target.value)} style={{ maxWidth: 200 }}/>
            <span style={{ fontSize: '.85rem', color: 'var(--color-text-secondary)' }}>
              {summary ? `${summary.meal_count} meal(s) logged` : ''}
            </span>
          </div>

          {loadingSummary ? (
            <div className="card" style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-tertiary)' }}>Loading summary...</div>
          ) : summary && summary.meal_count > 0 ? (
            <>
              {/* Macro cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
                {[
                  { label: 'Calories', val: summary.total_calories, unit: 'kcal', rda: 2000, color: '#f59e0b' },
                  { label: 'Protein', val: summary.total_protein_g, unit: 'g', rda: 50, color: '#3b82f6' },
                  { label: 'Carbs', val: summary.total_carbs_g, unit: 'g', rda: 275, color: '#8b5cf6' },
                  { label: 'Fat', val: summary.total_fat_g, unit: 'g', rda: 78, color: '#ef4444' },
                ].map((m) => {
                  const p = pct(m.val, m.rda);
                  return (
                    <div className="card" key={m.label} style={{ textAlign: 'center', padding: '1rem' }}>
                      <div style={{ fontSize: '.75rem', color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '.05em' }}>{m.label}</div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700, color: m.color, margin: '.25rem 0' }}>
                        {m.val != null ? (m.unit === 'kcal' ? Math.round(m.val) : m.val.toFixed(1)) : '0'}
                      </div>
                      <div style={{ fontSize: '.7rem', color: 'var(--color-text-secondary)' }}>{m.unit} · {p ?? 0}% DV</div>
                      <div style={{ background: 'var(--color-bg-secondary)', borderRadius: 4, height: 6, marginTop: '.5rem', overflow: 'hidden' }}>
                        <div style={{ width: `${Math.min(p || 0, 100)}%`, height: '100%', background: m.color, borderRadius: 4 }}/>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Full nutrient breakdown */}
              <div className="card">
                <NutrientBreakdown nutrients={summary.nutrients} title="Complete Nutrient Breakdown — % Daily Value"/>
              </div>
            </>
          ) : (
            <div className="card" style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-secondary)' }}>
              No meals logged for this date. Add entries in the Food Log tab.
            </div>
          )}
        </div>
      )}

      {/* ═══════════ FOOD DETAIL MODAL ═══════════ */}
      {(selectedFood || loadingDetail) && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 1000,
          display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: '5vh', overflowY: 'auto' }}
          onClick={() => { setSelectedFood(null); setFoodDetail(null); }}>
          <div className="card" style={{ maxWidth: 600, width: '90vw', maxHeight: '85vh', overflowY: 'auto', margin: '1rem' }}
            onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '.75rem' }}>
              <div>
                <h2 style={{ margin: 0, fontSize: '1.1rem' }}>{selectedFood}</h2>
                {foodDetail && (
                  <div style={{ fontSize: '.75rem', color: 'var(--color-text-tertiary)', marginTop: '.25rem' }}>
                    FDC ID: {foodDetail.fdc_id} · {foodDetail.data_type}
                    {foodDetail.food_category ? ` · ${foodDetail.food_category}` : ''}
                  </div>
                )}
              </div>
              <button onClick={() => { setSelectedFood(null); setFoodDetail(null); }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '.25rem' }}>
                <X size={18}/>
              </button>
            </div>
            {loadingDetail ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-tertiary)' }}>Loading nutrient data...</div>
            ) : foodDetail ? (
              <>
                {foodDetail.portions?.length > 0 && (
                  <div style={{ marginBottom: '.75rem', padding: '.5rem .75rem', background: 'var(--color-bg-secondary)', borderRadius: 8, fontSize: '.8rem' }}>
                    <strong>Portions:</strong> {foodDetail.portions.map((p) => `${p.description} (${p.gram_weight}g)`).join(' · ')}
                  </div>
                )}
                <NutrientBreakdown nutrients={foodDetail.nutrient_breakdown} title={`Nutrients per 100g — ${foodDetail.nutrient_breakdown.length} total`}/>
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#ef4444' }}>Failed to load nutrient data.</div>
            )}
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
