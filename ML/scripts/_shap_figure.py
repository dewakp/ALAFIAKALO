"""
Generate SHAP summary plots for top clinical risk models.
Produces a multi-panel figure for the paper.
"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
import shap
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

ML = Path(__file__).resolve().parent.parent
DATA_FEAT = ML / 'data' / 'features'
MODEL_DIR = ML / 'models' / 'clinical_risk'
OUT = DATA_FEAT

# Limit samples for faster SHAP + rendering
MAX_SHAP_SAMPLES = 300

# ── Load manifest ──
with open(MODEL_DIR / 'manifest.json') as f:
    manifest = json.load(f)

# ── Load feature matrix ──
fm = pd.read_csv(DATA_FEAT / 'clinical_risk_features.csv')
print(f"Feature matrix: {fm.shape}")

# ── Pick the most clinically interesting classification targets ──
# Choose 3 that span different risk domains AND are tree-based (for TreeExplainer)
# Hypotension (hemodynamic), Low Hemoglobin (hematologic), High PTH (endocrine)
shap_targets = ['hypotension', 'low_hemoglobin', 'high_pth']
nice_names = {
    'hypotension':    'Intradialytic Hypotension',
    'low_hemoglobin': 'Low Hemoglobin (<10 g/dL)',
    'high_pth':       'High PTH (>300 pg/mL)',
}

# ── Load risk labels ──
risk_labels = pd.read_csv(DATA_FEAT / 'risk_labels.csv')
print(f"Risk labels: {risk_labels.shape}, cols: {list(risk_labels.columns)[:15]}")

# Find which columns correspond to our targets
label_cols = {}
for t in shap_targets:
    candidates = [c for c in risk_labels.columns if t in c.lower()]
    if candidates:
        label_cols[t] = candidates[0]
        print(f"  {t} → {candidates[0]} (prevalence: {risk_labels[candidates[0]].mean():.3f})")
    else:
        print(f"  {t} → NOT FOUND in risk_labels!")

# ── Get features list from manifest ──
feature_names = manifest[shap_targets[0]]['features']
print(f"Features per model: {len(feature_names)}")

# Some features may not be in feature matrix; find available
available = [f for f in feature_names if f in fm.columns]
missing = [f for f in feature_names if f not in fm.columns]
if missing:
    print(f"  Missing features (will fill NaN): {missing[:10]}...")

# Build X matrix with all features, filling missing with NaN
X = pd.DataFrame()
for f in feature_names:
    if f in fm.columns:
        X[f] = fm[f].values
    else:
        X[f] = np.nan
print(f"X shape: {X.shape}")

# Sample for speed
if len(X) > MAX_SHAP_SAMPLES:
    idx_sample = np.random.RandomState(42).choice(len(X), MAX_SHAP_SAMPLES, replace=False)
    X = X.iloc[idx_sample].reset_index(drop=True)
    print(f"Sampled X to {X.shape}")

# ── Generate SHAP values for each target ──
fig, axes = plt.subplots(1, 3, figsize=(22, 7))

for idx, target in enumerate(shap_targets):
    ax = axes[idx]
    info = manifest[target]
    algo = info['algorithm']
    
    # Load pipeline
    pipe_path = MODEL_DIR / info['pipeline_file']
    pipe = joblib.load(pipe_path)
    print(f"\n{'='*60}")
    print(f"Target: {target} ({algo})")
    print(f"  Pipeline steps: {[s[0] for s in pipe.steps]}")
    
    # Get the model from pipeline
    # Pipeline typically: imputer → scaler → model
    model = pipe.steps[-1][1]
    
    # Transform X through preprocessing steps (all but last)
    X_transformed = X.copy()
    for step_name, step_transformer in pipe.steps[:-1]:
        X_transformed = pd.DataFrame(
            step_transformer.transform(X_transformed),
            columns=feature_names
        )
    
    # SHAP
    try:
        if hasattr(model, 'estimators_') or hasattr(model, 'n_estimators'):
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X_transformed)
            # For binary, may return list [class0, class1]
            if isinstance(shap_values, list):
                shap_values = shap_values[1]
            elif shap_values.ndim == 3:
                shap_values = shap_values[:, :, 1]
        else:
            # KernelExplainer for non-tree models
            X_bg = shap.sample(X_transformed, min(100, len(X_transformed)))
            def predict_proba_fn(x):
                return model.predict_proba(x)
            explainer = shap.KernelExplainer(predict_proba_fn, X_bg)
            sample_idx = np.random.choice(len(X_transformed), min(200, len(X_transformed)), replace=False)
            X_sample = X_transformed.iloc[sample_idx]
            shap_values = explainer.shap_values(X_sample, nsamples=100)
            if isinstance(shap_values, list):
                shap_values = shap_values[1]
            X_transformed = X_sample  # match shapes
        
        print(f"  SHAP values shape: {shap_values.shape}")
        
        # Clean up feature names for display
        display_names = []
        for f in feature_names:
            name = f.replace('pw_', 'Pathway: ').replace('lab_', 'Lab: ')
            name = name.replace('rdg_', 'Reading: ').replace('dial_', 'Dial: ')
            name = name.replace('nutr_', 'Nutr: ').replace('med_', 'Med: ')
            name = name.replace('_', ' ')
            # Truncate long names
            if len(name) > 35:
                name = name[:33] + '..'
            display_names.append(name)
        
        X_display = X_transformed.copy()
        X_display.columns = display_names
        
        plt.sca(ax)
        shap.summary_plot(
            shap_values, X_display,
            max_display=15, show=False, plot_size=None,
            color_bar=True
        )
        ax.set_title(nice_names[target], fontsize=13, fontweight='bold', pad=10)
        ax.set_xlabel('SHAP value (impact on model output)', fontsize=10)
        
    except Exception as e:
        print(f"  SHAP FAILED: {e}")
        import traceback
        traceback.print_exc()
        ax.text(0.5, 0.5, f"SHAP failed:\n{str(e)[:60]}", 
                ha='center', va='center', transform=ax.transAxes, fontsize=10)
        ax.set_title(nice_names[target], fontsize=13, fontweight='bold')

plt.tight_layout(w_pad=3)
plt.savefig(OUT / 'shap_summary.png', dpi=150, bbox_inches='tight',
            facecolor='white', edgecolor='none')
print(f"\n✅ Saved: {OUT / 'shap_summary.png'}")
print(f"   Size: {(OUT / 'shap_summary.png').stat().st_size / 1e6:.1f} MB")
