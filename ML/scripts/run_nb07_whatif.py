#!/usr/bin/env python3
"""
NB07 What-If Clinical Simulator — Standalone Script
====================================================
Runs all 15 code cells from 07_whatif_simulator.ipynb as a single script.
Fixes the forward-dependency bug in the notebook (Cell 7b references
heatmap_* and traj which are created in Cells 8-9).

Correct execution order:
  1-7  → Imports, engine, scenarios, sweeps, sweep viz
  8    → Trajectory (produces `traj`)
  9    → Dialysate heatmap (produces `heatmap_*`, `bath_*_range`)
  7b   → Enhanced viz (needs sweep_results, comp_df, heatmap_*, traj)
  10-14 → Food DB, food what-if, historical overlay, MATLAB export, summary
"""

import numpy as np
import pandas as pd
import joblib
import json
import warnings
from pathlib import Path
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend — no display needed
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings('ignore')

# ── Paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR   = PROJECT_ROOT / 'models'
DATA_DIR     = PROJECT_ROOT / 'data'
PROCESSED    = DATA_DIR / 'processed'
FEATURES_DIR = DATA_DIR / 'features'

print('=' * 70)
print('   NB07 What-If Clinical Simulator — Standalone Execution')
print('=' * 70)
print(f'  PROJECT_ROOT: {PROJECT_ROOT}')
print(f'  MODELS_DIR:   {MODELS_DIR}')
print(f'  FEATURES_DIR: {FEATURES_DIR}')

# ═══════════════════════════════════════════════════════════
# CELL 1: Load All Models + Historical Data
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 1: Loading models & data...')
print('─' * 70)

holistic_model = joblib.load(MODELS_DIR / 'holistic_health_model.joblib')
FEATURE_NAMES = list(holistic_model['pipeline'].feature_names_in_)
print(f'  Holistic model: {len(FEATURE_NAMES)} features, R²={holistic_model["metrics"]["R²"]:.3f}')

RISK_MODELS = {}
risk_names = ['anemia', 'gi_distress', 'hyperkalemia', 'hyperparathyroid',
              'hypocalcemia', 'hypokalemia', 'intradialytic_hypotension',
              'iron_deficiency', 'malnutrition', 'metabolic_acidosis', 'poor_health']
for rn in risk_names:
    try:
        RISK_MODELS[rn] = joblib.load(MODELS_DIR / f'risk_{rn}_model.joblib')
        print(f'  risk_{rn}: loaded')
    except Exception as e:
        print(f'  risk_{rn}: SKIP ({e})')

with open(MODELS_DIR / 'HEBCS_pathway_definitions.json') as f:
    PATHWAY_DEFS = json.load(f)
print(f'  HEBCS pathways: {list(PATHWAY_DEFS.keys())}')

print('\nLoading historical data...')
df_features = pd.read_csv(FEATURES_DIR / 'health_features.csv', parse_dates=['date'], index_col='date')
df_scores   = pd.read_csv(FEATURES_DIR / 'health_scores.csv', parse_dates=['date'], index_col='date')
df_nutrition = pd.read_csv(PROCESSED / 'unified_nutrition.csv', low_memory=False)
df_nutrition['date'] = pd.to_datetime(df_nutrition['date'], errors='coerce')
df_sessions = pd.read_csv(PROCESSED / 'dialysis_sessions.csv', low_memory=False)
df_sessions['session_date'] = pd.to_datetime(df_sessions['session_date'], errors='coerce')
df_labs = pd.read_csv(PROCESSED / 'unified_labs.csv', low_memory=False)
df_labs['date'] = pd.to_datetime(df_labs['date'], errors='coerce')
df_wellness = pd.read_csv(FEATURES_DIR / 'HEBCS_wellness_daily.csv', index_col=0, parse_dates=True)

print(f'  Features: {df_features.shape}')
print(f'  Scores: {df_scores.shape}')
print(f'  Nutrition rows: {len(df_nutrition)}')
print(f'  Dialysis sessions: {len(df_sessions)}')
print(f'  Lab results: {len(df_labs)}')
print(f'  Wellness days: {len(df_wellness)}')

BASELINE = df_features[FEATURE_NAMES].median().to_dict()
print(f'\nBaseline feature vector computed (median of {len(df_features)} days)')

# ═══════════════════════════════════════════════════════════
# CELL 2: What-If Engine — Core Prediction Functions
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 2: Defining What-If engine functions...')
print('─' * 70)

def build_feature_vector(scenario: dict, baseline: dict = None) -> pd.DataFrame:
    if baseline is None:
        baseline = BASELINE
    vec = baseline.copy()

    NUTRITION_MAP = {
        'calories': 'nutr_calories', 'protein': 'nutr_protein_g',
        'carbs': 'nutr_carbs_g', 'fat': 'nutr_fat_g',
        'fiber': 'nutr_fiber_g', 'sugar': 'nutr_sugar_g',
        'sodium': 'nutr_sodium_mg', 'potassium': 'nutr_potassium_mg',
        'calcium': 'nutr_calcium_mg', 'iron': 'nutr_iron_mg',
        'phosphorus': 'nutr_phosphorus_mg',
        'cholesterol': 'nutr_cholesterol_mg',
        'vitamin_d': 'nutr_vitamin_d_mcg', 'vitamin_b12': 'nutr_vitamin_b12_mcg',
        'folic_acid': 'nutr_folic_acid_mcg',
    }
    DIALYSIS_MAP = {
        'pre_weight': 'dial_pre_weight', 'post_weight': 'dial_post_weight',
        'blood_flow': 'dial_avg_blood_flow', 'dialysate_rate': 'dial_avg_dialysate_rate',
        'bath_ca': 'dial_bath_ca', 'bath_k': 'dial_bath_k', 'bath_na': 'dial_bath_na',
        'session_duration_min': 'dial_total_time_min',
        'pre_bp_sys': 'dial_pre_bp_sys', 'pre_bp_dia': 'dial_pre_bp_dia',
        'post_bp_sys': 'dial_post_bp_sys', 'post_bp_dia': 'dial_post_bp_dia',
        'uf_goal': 'dial_uf_total', 'ktv': 'dial_ktv_actual',
    }
    MED_MAP = {
        'calcium_carbonate_doses': 'med_calcium_carbonate_doses',
        'calcitriol_doses': 'med_calcitriol_doses',
        'epo_doses': 'med_epo_doses',
        'iron_doses': 'med_iron_doses',
        'heparin_doses': 'med_heparin_doses',
    }
    ACTIVITY_MAP = {
        'sessions_7d': 'activity_dial_sessions_7d',
        'active_days_7d': 'activity_active_days_7d',
        'rest_streak': 'activity_rest_days_streak',
    }
    ALL_MAPS = {**NUTRITION_MAP, **DIALYSIS_MAP, **MED_MAP, **ACTIVITY_MAP}

    for user_key, value in scenario.items():
        if user_key in ALL_MAPS:
            feat_name = ALL_MAPS[user_key]
            if feat_name in vec:
                vec[feat_name] = value

    if 'pre_weight' in scenario and 'post_weight' in scenario:
        wl = scenario['pre_weight'] - scenario['post_weight']
        if 'dial_weight_loss_kg' in vec:
            vec['dial_weight_loss_kg'] = wl
    if 'pre_bp_sys' in scenario and 'pre_bp_dia' in scenario:
        mmap = scenario['pre_bp_dia'] + (scenario['pre_bp_sys'] - scenario['pre_bp_dia']) / 3
        if 'dial_pre_map' in vec:
            vec['dial_pre_map'] = mmap

    row = pd.DataFrame([vec])[FEATURE_NAMES]
    return row


def predict_whatif(scenario: dict, verbose: bool = True) -> dict:
    X = build_feature_vector(scenario)
    results = {}
    pipeline = holistic_model['pipeline']
    score = pipeline.predict(X)[0]
    results['holistic_score'] = np.clip(score, 0, 100)

    for risk_name, model_pkg in RISK_MODELS.items():
        try:
            pipe = model_pkg['pipeline']
            prob = pipe.predict_proba(X)[0]
            risk_prob = prob[1] if len(prob) > 1 else prob[0]
            results[f'risk_{risk_name}'] = risk_prob
        except Exception:
            try:
                pred = pipe.predict(X)[0]
                results[f'risk_{risk_name}'] = float(pred)
            except:
                results[f'risk_{risk_name}'] = np.nan

    if verbose:
        print(f"\n{'═'*60}")
        print(f"  WHAT-IF PREDICTION RESULTS")
        print(f"{'═'*60}")
        print(f"\n  Holistic Health Score: {results['holistic_score']:.1f} / 100")
        print(f"\n  Risk Probabilities:")
        for k, v in sorted(results.items()):
            if k.startswith('risk_') and not np.isnan(v):
                name = k.replace('risk_', '').replace('_', ' ').title()
                bar = '█' * int(v * 30) + '░' * (30 - int(v * 30))
                flag = ' ⚠️' if v > 0.5 else ' ✅' if v < 0.2 else ''
                print(f"    {name:<30} {bar} {v:.1%}{flag}")
    return results


def compare_scenarios(scenarios: dict) -> pd.DataFrame:
    all_results = {}
    for name, sc in scenarios.items():
        all_results[name] = predict_whatif(sc, verbose=False)
    df = pd.DataFrame(all_results).T
    df.index.name = 'Scenario'
    return df


print('What-If engine ready.')
print(f'  {len(FEATURE_NAMES)} features, {len(RISK_MODELS)} risk models + holistic score')

# ═══════════════════════════════════════════════════════════
# CELL 3: Single Scenario Prediction
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 3: Single scenario prediction...')
print('─' * 70)

scenario_today = {
    'calories': 2200, 'protein': 65, 'sodium': 1800, 'potassium': 1500,
    'phosphorus': 700, 'calcium': 600, 'iron': 8, 'carbs': 280,
    'fat': 70, 'fiber': 20, 'sugar': 50,
    'pre_weight': 55.2, 'post_weight': 53.0, 'blood_flow': 400,
    'dialysate_rate': 500, 'bath_ca': 2.5, 'bath_k': 2.0, 'bath_na': 140,
    'session_duration_min': 240, 'pre_bp_sys': 140, 'pre_bp_dia': 85, 'ktv': 1.4,
    'calcium_carbonate_doses': 3, 'calcitriol_doses': 1,
    'epo_doses': 0, 'iron_doses': 0, 'heparin_doses': 1,
    'sessions_7d': 4, 'active_days_7d': 5, 'rest_streak': 1,
}
results = predict_whatif(scenario_today)

# ═══════════════════════════════════════════════════════════
# CELL 4: Compare Scenarios — Dietary Impact
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 4: Multi-scenario comparison...')
print('─' * 70)

scenarios = {
    'Optimal Diet': {
        'calories': 2100, 'protein': 60, 'sodium': 1500,
        'potassium': 1200, 'phosphorus': 600, 'calcium': 800,
        'iron': 10, 'fiber': 25, 'sugar': 30,
        'pre_weight': 54.5, 'post_weight': 53.0,
        'blood_flow': 400, 'bath_k': 2.0, 'bath_ca': 2.5,
        'calcium_carbonate_doses': 3, 'calcitriol_doses': 1,
    },
    'High Sodium Day': {
        'calories': 2400, 'protein': 55, 'sodium': 3500,
        'potassium': 1800, 'phosphorus': 900, 'calcium': 400,
        'iron': 5, 'fiber': 12, 'sugar': 80,
        'pre_weight': 56.0, 'post_weight': 53.0,
        'blood_flow': 400, 'bath_k': 2.0, 'bath_ca': 2.5,
        'calcium_carbonate_doses': 2, 'calcitriol_doses': 1,
    },
    'High K+ (Risky)': {
        'calories': 2000, 'protein': 70, 'sodium': 2000,
        'potassium': 3500, 'phosphorus': 1000, 'calcium': 500,
        'iron': 6, 'fiber': 15, 'sugar': 60,
        'pre_weight': 55.0, 'post_weight': 53.5,
        'blood_flow': 350, 'bath_k': 3.0, 'bath_ca': 2.5,
        'calcium_carbonate_doses': 1, 'calcitriol_doses': 0,
    },
    'Low Protein (Risk)': {
        'calories': 1500, 'protein': 25, 'sodium': 1800,
        'potassium': 1000, 'phosphorus': 400, 'calcium': 300,
        'iron': 4, 'fiber': 10, 'sugar': 70,
        'pre_weight': 54.0, 'post_weight': 53.0,
        'blood_flow': 400, 'bath_k': 2.0, 'bath_ca': 2.5,
        'calcium_carbonate_doses': 3, 'calcitriol_doses': 1,
    },
    'Missed Session': {
        'calories': 2200, 'protein': 60, 'sodium': 2000,
        'potassium': 2000, 'phosphorus': 800, 'calcium': 600,
        'iron': 8, 'fiber': 18, 'sugar': 45,
        'sessions_7d': 2, 'rest_streak': 3,
    },
}

comp_df = compare_scenarios(scenarios)
print(f"\n{'═'*90}")
print("  SCENARIO COMPARISON")
print('═' * 90)
print(f"\n{'Scenario':<25} {'Health':>7} {'Hypotn':>7} {'Anemia':>7} {'HyperK':>7} "
      f"{'Acidosis':>8} {'GI':>7} {'Malnutr':>8}")
print('─' * 90)
for sc_name, row in comp_df.iterrows():
    print(f"{sc_name:<25} {row['holistic_score']:>6.1f} "
          f"{row.get('risk_intradialytic_hypotension', 0):>6.1%} "
          f"{row.get('risk_anemia', 0):>6.1%} "
          f"{row.get('risk_hyperkalemia', 0):>6.1%} "
          f"{row.get('risk_metabolic_acidosis', 0):>7.1%} "
          f"{row.get('risk_gi_distress', 0):>6.1%} "
          f"{row.get('risk_malnutrition', 0):>7.1%}")

# ═══════════════════════════════════════════════════════════
# CELL 5: Visualization — Scenario Comparison
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 5: Scenario comparison visualization...')
print('─' * 70)

fig, axes = plt.subplots(1, 2, figsize=(18, 7))

risk_cols = [c for c in comp_df.columns if c.startswith('risk_')]
risk_labels = [c.replace('risk_', '').replace('_', ' ').title() for c in risk_cols]

n_scenarios = len(comp_df)
n_risks = len(risk_cols)
x = np.arange(n_risks)
width = 0.8 / n_scenarios
colors = plt.cm.Set2(np.linspace(0, 1, n_scenarios))

ax = axes[0]
for i, (sc_name, row) in enumerate(comp_df.iterrows()):
    vals = [row[c] for c in risk_cols]
    ax.bar(x + i * width, vals, width, label=sc_name, color=colors[i], alpha=0.85)
ax.set_xticks(x + width * (n_scenarios - 1) / 2)
ax.set_xticklabels(risk_labels, rotation=45, ha='right', fontsize=8)
ax.set_ylabel('Risk Probability')
ax.set_title('Risk Comparison Across Scenarios', fontweight='bold')
ax.axhline(y=0.5, color='red', linestyle='--', alpha=0.4, label='High Risk (50%)')
ax.axhline(y=0.2, color='orange', linestyle='--', alpha=0.3, label='Moderate (20%)')
ax.legend(loc='upper left', fontsize=7, ncol=2)
ax.set_ylim(0, 1.05)

ax = axes[1]
sc_names = list(comp_df.index)
scores = comp_df['holistic_score'].values
bar_colors = ['#4CAF50' if s >= 75 else '#FF9800' if s >= 50 else '#F44336' for s in scores]
bars = ax.barh(sc_names, scores, color=bar_colors, alpha=0.85, edgecolor='white')
for bar, sc in zip(bars, scores):
    ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
            f'{sc:.1f}', va='center', fontweight='bold', fontsize=11)
ax.set_xlabel('Holistic Health Score (0-100)')
ax.set_title('Predicted Health Score by Scenario', fontweight='bold')
ax.axvline(x=75, color='green', linestyle='--', alpha=0.3, label='Good')
ax.axvline(x=50, color='red', linestyle='--', alpha=0.3, label='Warning')
ax.legend()
ax.set_xlim(0, 105)

plt.suptitle('NB07 What-If Clinical Simulator — Scenario Analysis',
             fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig(FEATURES_DIR / 'whatif_scenario_comparison.png', dpi=150, bbox_inches='tight')
plt.close()
print('  Saved: whatif_scenario_comparison.png')

# ═══════════════════════════════════════════════════════════
# CELL 6: Sensitivity Sweeps
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 6: Sensitivity sweeps...')
print('─' * 70)

SWEEP_VARS = {
    'potassium':          (500,  5000, 50, 'mg',    1000, 2000),
    'sodium':             (500,  5000, 50, 'mg',    1000, 2000),
    'phosphorus':         (200,  2000, 50, 'mg',    400,  800),
    'protein':            (10,   120,  50, 'g',     50,   70),
    'calories':           (800,  4000, 50, 'kcal',  1800, 2500),
    'blood_flow':         (200,  500,  50, 'mL/min',350,  450),
    'bath_k':             (1.0,  4.0,  50, 'mEq/L', 1.5,  2.5),
    'pre_bp_sys':         (90,   200,  50, 'mmHg',  120,  150),
    'session_duration_min':(120, 360,  50, 'min',   180,  270),
}

sweep_results = {}
for var_name, (vmin, vmax, nsteps, unit, rlo, rhi) in SWEEP_VARS.items():
    values = np.linspace(vmin, vmax, nsteps)
    scores = []
    risks_hyper_k = []
    risks_hypo = []
    for v in values:
        sc = {var_name: v}
        r = predict_whatif(sc, verbose=False)
        scores.append(r['holistic_score'])
        risks_hyper_k.append(r.get('risk_hyperkalemia', 0))
        risks_hypo.append(r.get('risk_intradialytic_hypotension', 0))
    sweep_results[var_name] = {
        'values': values, 'scores': scores,
        'risk_hyperkalemia': risks_hyper_k,
        'risk_hypotension': risks_hypo,
        'unit': unit, 'range': (rlo, rhi)
    }
    print(f'  {var_name}: done')

print(f'Completed {len(sweep_results)} sensitivity sweeps × {nsteps} steps each')

# ═══════════════════════════════════════════════════════════
# CELL 7: Plot Sensitivity Curves
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 7: Sensitivity visualization...')
print('─' * 70)

n_vars = len(sweep_results)
ncols = 3
nrows = (n_vars + ncols - 1) // ncols
fig, axes = plt.subplots(nrows, ncols, figsize=(18, 4 * nrows))
axes = axes.flatten()

for idx, (var_name, data) in enumerate(sweep_results.items()):
    ax = axes[idx]
    vals = data['values']
    rlo, rhi = data['range']
    color1 = '#2196F3'
    ax.plot(vals, data['scores'], '-', color=color1, linewidth=2, label='Health Score')
    ax.set_ylabel('Health Score', color=color1, fontsize=9)
    ax.tick_params(axis='y', labelcolor=color1)
    ax.set_ylim(0, 100)
    ax.axvspan(rlo, rhi, alpha=0.12, color='green', label='Target range')
    ax2 = ax.twinx()
    color2 = '#F44336'
    if var_name in ('potassium', 'bath_k'):
        ax2.plot(vals, data['risk_hyperkalemia'], '--', color=color2, linewidth=1.5, alpha=0.7, label='HyperK risk')
    else:
        ax2.plot(vals, data['risk_hypotension'], '--', color=color2, linewidth=1.5, alpha=0.7, label='Hypotn risk')
    ax2.set_ylabel('Risk Probability', color=color2, fontsize=9)
    ax2.tick_params(axis='y', labelcolor=color2)
    ax2.set_ylim(0, 1)
    ax.set_xlabel(f'{var_name.replace("_", " ").title()} ({data["unit"]})', fontsize=9)
    ax.set_title(f'{var_name.replace("_", " ").title()}', fontweight='bold', fontsize=10)
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc='best', fontsize=7)

for idx in range(n_vars, len(axes)):
    axes[idx].set_visible(False)

plt.suptitle('Sensitivity Analysis — Variable Sweeps (ESRD Target Range in Green)',
             fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig(FEATURES_DIR / 'whatif_sensitivity_sweeps.png', dpi=150, bbox_inches='tight')
plt.close()
print('  Saved: whatif_sensitivity_sweeps.png')

# ═══════════════════════════════════════════════════════════
# CELL 8: Multi-Day Trajectory Simulation
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 8: 14-day trajectory simulation...')
print('─' * 70)

def simulate_trajectory(daily_scenarios, start_date='2026-02-19', carry_forward=True):
    start = pd.Timestamp(start_date)
    trajectory = []
    for i, scenario in enumerate(daily_scenarios):
        date = start + timedelta(days=i)
        results = predict_whatif(scenario, verbose=False)
        results['date'] = date
        results['day'] = i + 1
        trajectory.append(results)
    df_traj = pd.DataFrame(trajectory)
    df_traj.set_index('date', inplace=True)
    return df_traj

good_day = {
    'calories': 2100, 'protein': 60, 'sodium': 1500, 'potassium': 1200,
    'phosphorus': 600, 'calcium': 800, 'iron': 10, 'fiber': 25, 'sugar': 30,
    'pre_weight': 54.5, 'post_weight': 53.0, 'blood_flow': 400,
    'bath_k': 2.0, 'bath_ca': 2.5, 'session_duration_min': 240,
    'calcium_carbonate_doses': 3, 'calcitriol_doses': 1,
    'sessions_7d': 4, 'active_days_7d': 5,
}
bad_day = {
    'calories': 3200, 'protein': 30, 'sodium': 3500, 'potassium': 3000,
    'phosphorus': 1200, 'calcium': 300, 'iron': 3, 'fiber': 8, 'sugar': 100,
    'pre_weight': 57.0, 'post_weight': 53.0, 'blood_flow': 300,
    'bath_k': 3.0, 'bath_ca': 2.0, 'session_duration_min': 180,
    'calcium_carbonate_doses': 0, 'calcitriol_doses': 0,
    'sessions_7d': 2, 'active_days_7d': 2,
}

daily_plans = [good_day] * 7 + [bad_day] * 7
traj = simulate_trajectory(daily_plans)

fig, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

ax = axes[0]
ax.plot(traj.index, traj['holistic_score'], 'o-', color='#2196F3', linewidth=2, markersize=8)
ax.fill_between(traj.index, 0, traj['holistic_score'], alpha=0.15, color='#2196F3')
ax.axhline(75, color='green', linestyle='--', alpha=0.4, label='Good')
ax.axhline(50, color='red', linestyle='--', alpha=0.4, label='Warning')
ax.axvspan(traj.index[0], traj.index[6], alpha=0.08, color='green', label='Good week')
ax.axvspan(traj.index[7], traj.index[13], alpha=0.08, color='red', label='Bad week')
ax.set_ylabel('Holistic Health Score')
ax.set_title('14-Day What-If Trajectory: Good Week → Bad Week', fontweight='bold')
ax.legend(loc='lower left')
ax.set_ylim(0, 100)

ax = axes[1]
risk_keys = ['risk_hyperkalemia', 'risk_anemia', 'risk_intradialytic_hypotension',
             'risk_malnutrition', 'risk_metabolic_acidosis']
colors_risk = ['#F44336', '#FF9800', '#9C27B0', '#795548', '#607D8B']
for rk, clr in zip(risk_keys, colors_risk):
    if rk in traj.columns:
        label = rk.replace('risk_', '').replace('_', ' ').title()
        ax.plot(traj.index, traj[rk], 'o-', color=clr, linewidth=1.5, markersize=5, label=label)
ax.axhline(0.5, color='red', linestyle='--', alpha=0.3, label='High Risk')
ax.axvspan(traj.index[0], traj.index[6], alpha=0.08, color='green')
ax.axvspan(traj.index[7], traj.index[13], alpha=0.08, color='red')
ax.set_ylabel('Risk Probability')
ax.set_xlabel('Date')
ax.set_title('Risk Trajectories Over 14 Days', fontweight='bold')
ax.legend(loc='upper left', fontsize=8, ncol=2)
ax.set_ylim(0, 1.05)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))

plt.tight_layout()
plt.savefig(FEATURES_DIR / 'whatif_trajectory_14d.png', dpi=150, bbox_inches='tight')
plt.close()
print('  Saved: whatif_trajectory_14d.png')

# ═══════════════════════════════════════════════════════════
# CELL 9: Dialysate Composition 2D Heatmap
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 9: Dialysate heatmap (25x25 = 625 predictions)...')
print('─' * 70)

bath_k_range = np.linspace(1.0, 4.0, 25)
bath_ca_range = np.linspace(1.5, 3.5, 25)

heatmap_health = np.zeros((len(bath_ca_range), len(bath_k_range)))
heatmap_hypoK = np.zeros_like(heatmap_health)
heatmap_hyperK = np.zeros_like(heatmap_health)

for i, ca in enumerate(bath_ca_range):
    for j, k in enumerate(bath_k_range):
        sc = {'bath_ca': ca, 'bath_k': k, 'blood_flow': 400, 'session_duration_min': 240}
        r = predict_whatif(sc, verbose=False)
        heatmap_health[i, j] = r['holistic_score']
        heatmap_hypoK[i, j] = r.get('risk_hypokalemia', 0)
        heatmap_hyperK[i, j] = r.get('risk_hyperkalemia', 0)
    if (i + 1) % 5 == 0:
        print(f'    Row {i+1}/{len(bath_ca_range)} done')

fig, axes = plt.subplots(1, 3, figsize=(20, 6))
for ax, data, title, cmap in [
    (axes[0], heatmap_health, 'Holistic Health Score', 'RdYlGn'),
    (axes[1], heatmap_hypoK, 'Hypokalemia Risk', 'YlOrRd'),
    (axes[2], heatmap_hyperK, 'Hyperkalemia Risk', 'YlOrRd'),
]:
    im = ax.imshow(data, origin='lower', aspect='auto', cmap=cmap,
                   extent=[bath_k_range[0], bath_k_range[-1],
                           bath_ca_range[0], bath_ca_range[-1]])
    ax.set_xlabel('Bath K+ (mEq/L)')
    ax.set_ylabel('Bath Ca2+ (mEq/L)')
    ax.set_title(title, fontweight='bold')
    plt.colorbar(im, ax=ax, shrink=0.8)
    ax.plot(2.0, 2.5, 'w*', markersize=15, markeredgecolor='black', label='Usual Rx')
    ax.legend(loc='upper right', fontsize=8)

plt.suptitle('Dialysate Composition What-If — Bath K+ vs Ca2+ Interaction',
             fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig(FEATURES_DIR / 'whatif_dialysate_heatmap.png', dpi=150, bbox_inches='tight')
plt.close()
print('  Saved: whatif_dialysate_heatmap.png')

# ═══════════════════════════════════════════════════════════
# CELL 7b: Enhanced-Scale Visualizations
#   Now safe because traj, heatmap_*, bath_*_range are defined
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 7b: Enhanced-scale visualizations...')
print('─' * 70)

from matplotlib.colors import LogNorm, SymLogNorm
from matplotlib.ticker import SymmetricalLogLocator, LogLocator, FuncFormatter

# 1. Sensitivity: % delta from baseline + symlog risk
baseline_score = predict_whatif({}, verbose=False)['holistic_score']

n_vars = len(sweep_results)
ncols = 3
nrows = (n_vars + ncols - 1) // ncols
fig, axes = plt.subplots(nrows, ncols, figsize=(18, 4.5 * nrows))
axes = axes.flatten()

for idx, (var_name, data) in enumerate(sweep_results.items()):
    ax = axes[idx]
    vals = data['values']
    rlo, rhi = data['range']
    s = np.array(data['scores'])
    pct_delta = 100.0 * (s - baseline_score) / baseline_score
    color1 = '#2196F3'
    ax.plot(vals, pct_delta, '-', color=color1, linewidth=2, label='Health delta%')
    ax.axhline(0, color='gray', linewidth=0.8, linestyle='-')
    ax.set_ylabel('Health Score delta% from baseline', color=color1, fontsize=8)
    ax.tick_params(axis='y', labelcolor=color1)
    yabs = max(np.abs(pct_delta).max(), 0.5) * 1.15
    ax.set_ylim(-yabs, yabs)
    ax.fill_between(vals, 0, pct_delta, where=(pct_delta >= 0),
                     interpolate=True, alpha=0.15, color='green')
    ax.fill_between(vals, 0, pct_delta, where=(pct_delta < 0),
                     interpolate=True, alpha=0.15, color='red')
    ax.axvspan(rlo, rhi, alpha=0.10, color='green', label='Target range')
    ax2 = ax.twinx()
    color2 = '#F44336'
    if var_name in ('potassium', 'bath_k'):
        risk_data = np.array(data['risk_hyperkalemia'])
        rlabel = 'HyperK risk'
    else:
        risk_data = np.array(data['risk_hypotension'])
        rlabel = 'Hypotn risk'
    ax2.plot(vals, risk_data, '--', color=color2, linewidth=1.5, alpha=0.8, label=rlabel)
    ax2.set_yscale('symlog', linthresh=0.01)
    ax2.set_ylabel('Risk (symlog)', color=color2, fontsize=8)
    ax2.tick_params(axis='y', labelcolor=color2)
    ax2.set_ylim(0, 1)
    ax.set_xlabel(f'{var_name.replace("_"," ").title()} ({data["unit"]})', fontsize=9)
    ax.set_title(f'{var_name.replace("_"," ").title()}', fontweight='bold', fontsize=10)
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc='best', fontsize=7)

for idx in range(n_vars, len(axes)):
    axes[idx].set_visible(False)

plt.suptitle('Sensitivity Analysis — % delta from Baseline + SymLog Risk Axis',
             fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig(FEATURES_DIR / 'whatif_sensitivity_enhanced.png', dpi=150, bbox_inches='tight')
plt.close()
print('  Saved: whatif_sensitivity_enhanced.png')

# 2. Scenario comparison log10 risk bars
fig, axes = plt.subplots(1, 2, figsize=(18, 7))

ax = axes[0]
n_scenarios = len(comp_df)
n_risks = len(risk_cols)
x = np.arange(n_risks)
width = 0.8 / n_scenarios
colors = plt.cm.Set2(np.linspace(0, 1, n_scenarios))

for i, (sc_name, row) in enumerate(comp_df.iterrows()):
    vals = np.array([row[c] for c in risk_cols])
    vals_log = np.where(vals > 0, vals, 1e-6)
    ax.bar(x + i * width, vals_log, width, label=sc_name, color=colors[i], alpha=0.85)
ax.set_xticks(x + width * (n_scenarios - 1) / 2)
ax.set_xticklabels(risk_labels, rotation=45, ha='right', fontsize=8)
ax.set_ylabel('Risk Probability (log10 scale)')
ax.set_yscale('log')
ax.set_ylim(1e-4, 2)
ax.axhline(y=0.5, color='red', linestyle='--', alpha=0.4, label='High Risk')
ax.axhline(y=0.1, color='orange', linestyle='--', alpha=0.3, label='10%')
ax.axhline(y=0.01, color='green', linestyle='--', alpha=0.3, label='1%')
ax.set_title('Risk Comparison — Log10 Scale', fontweight='bold')
ax.legend(loc='lower left', fontsize=7, ncol=2)

ax = axes[1]
sc_names = list(comp_df.index)
scores = comp_df['holistic_score'].values
mean_sc = scores.mean()
deltas = scores - mean_sc
bar_colors = ['#4CAF50' if d >= 0 else '#F44336' for d in deltas]
bars = ax.barh(sc_names, deltas, color=bar_colors, alpha=0.85, edgecolor='white')
for bar, d, s in zip(bars, deltas, scores):
    x_pos = bar.get_width() + (0.15 if d >= 0 else -0.15)
    ha = 'left' if d >= 0 else 'right'
    ax.text(x_pos, bar.get_y() + bar.get_height()/2,
            f'{d:+.2f}  ({s:.1f})', va='center', ha=ha, fontweight='bold', fontsize=10)
ax.axvline(0, color='gray', linewidth=1)
ax.set_xlabel(f'delta from mean score ({mean_sc:.1f})')
ax.set_title('Health Score Deviation from Mean', fontweight='bold')

plt.suptitle('Scenario Analysis — Alternative Scales', fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig(FEATURES_DIR / 'whatif_scenario_log.png', dpi=150, bbox_inches='tight')
plt.close()
print('  Saved: whatif_scenario_log.png')

# 3. Dialysate heatmap LogNorm
fig, axes = plt.subplots(1, 3, figsize=(20, 6))
for ax, data_mat, title, cmap in [
    (axes[0], heatmap_health, 'Holistic Health Score', 'RdYlGn'),
    (axes[1], heatmap_hypoK,  'Hypokalemia Risk (LogNorm)', 'YlOrRd'),
    (axes[2], heatmap_hyperK, 'Hyperkalemia Risk (LogNorm)', 'YlOrRd'),
]:
    ext = [bath_k_range[0], bath_k_range[-1], bath_ca_range[0], bath_ca_range[-1]]
    if 'Risk' in title:
        vmin_r = max(data_mat[data_mat > 0].min(), 1e-5) if (data_mat > 0).any() else 1e-5
        vmax_r = max(data_mat.max(), vmin_r * 10)  # ensure vmax > vmin
        norm = LogNorm(vmin=vmin_r, vmax=vmax_r)
        im = ax.imshow(data_mat, origin='lower', aspect='auto',
                       cmap=cmap, norm=norm, extent=ext)
    else:
        med_h = np.median(data_mat)
        halfspan = max(data_mat.max() - med_h, med_h - data_mat.min(), 0.5)
        im = ax.imshow(data_mat, origin='lower', aspect='auto',
                       cmap=cmap, vmin=med_h - halfspan, vmax=med_h + halfspan,
                       extent=ext)
    ax.set_xlabel('Bath K+ (mEq/L)')
    ax.set_ylabel('Bath Ca2+ (mEq/L)')
    ax.set_title(title, fontweight='bold')
    plt.colorbar(im, ax=ax, shrink=0.8)
    ax.plot(2.0, 2.5, 'w*', markersize=15, markeredgecolor='black', label='Usual Rx')
    ax.legend(loc='upper right', fontsize=8)

plt.suptitle('Dialysate Composition — LogNorm Risk Colorbar', fontsize=13, fontweight='bold', y=1.04)
plt.tight_layout()
plt.savefig(FEATURES_DIR / 'whatif_dialysate_lognorm.png', dpi=150, bbox_inches='tight')
plt.close()
print('  Saved: whatif_dialysate_lognorm.png')

# 4. Trajectory symlog risk
fig, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

ax = axes[0]
hs = traj['holistic_score'].values
ax.plot(traj.index, hs, 'o-', color='#2196F3', linewidth=2, markersize=8)
ax.fill_between(traj.index, 0, hs, alpha=0.12, color='#2196F3')
ax.axhline(75, color='green', ls='--', alpha=0.4, label='Good')
ax.axhline(50, color='red', ls='--', alpha=0.4, label='Warning')
ax.axvspan(traj.index[0], traj.index[6], alpha=0.08, color='green', label='Good week')
ax.axvspan(traj.index[7], traj.index[13], alpha=0.08, color='red', label='Bad week')
ax.set_ylabel('Health Score')
ax.set_title('14-Day Trajectory — Health Score', fontweight='bold')
ax.legend(loc='lower left', fontsize=9)
ax.set_ylim(0, 100)

ax = axes[1]
risk_keys_traj = ['risk_hyperkalemia', 'risk_anemia', 'risk_intradialytic_hypotension',
                  'risk_malnutrition', 'risk_metabolic_acidosis']
colors_risk_t = ['#F44336', '#FF9800', '#9C27B0', '#795548', '#607D8B']
for rk, clr in zip(risk_keys_traj, colors_risk_t):
    if rk in traj.columns:
        label = rk.replace('risk_', '').replace('_', ' ').title()
        ax.plot(traj.index, traj[rk], 'o-', color=clr, linewidth=1.5,
                markersize=5, label=label)
ax.set_yscale('symlog', linthresh=0.01)
ax.set_ylabel('Risk Probability (symlog)')
ax.set_xlabel('Date')
ax.axhline(0.5, color='red', ls='--', alpha=0.3, label='High Risk')
ax.axhline(0.1, color='orange', ls='--', alpha=0.3, label='10%')
ax.axhline(0.01, color='gray', ls=':', alpha=0.4, label='1%')
ax.axvspan(traj.index[0], traj.index[6], alpha=0.08, color='green')
ax.axvspan(traj.index[7], traj.index[13], alpha=0.08, color='red')
ax.set_title('Risk Trajectories — SymLog Scale', fontweight='bold')
ax.legend(loc='upper left', fontsize=8, ncol=2)
ax.set_ylim(0, 1.05)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))

plt.tight_layout()
plt.savefig(FEATURES_DIR / 'whatif_trajectory_symlog.png', dpi=150, bbox_inches='tight')
plt.close()
print('  Saved: whatif_trajectory_symlog.png')
print('\n  All 4 enhanced-scale visualizations saved.')

# ═══════════════════════════════════════════════════════════
# CELL 10: Food Item Database & Lookup
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 10: Building food nutrient database...')
print('─' * 70)

nutrient_keys = ['calories', 'protein', 'carbs', 'fat', 'fiber', 'sugar',
                 'sodium', 'potassium', 'calcium', 'iron', 'phosphorus',
                 'cholesterol', 'vitamin_d', 'vitamin_b12', 'folic_acid']

backfill_path = DATA_DIR / 'nutrition_backfill' / 'nutrition_backfilled.csv'
if backfill_path.exists():
    df_backfill = pd.read_csv(backfill_path)
    food_db = []
    for _, row in df_backfill.iterrows():
        try:
            items = json.loads(row['items_json'])
            for item in items:
                food_db.append(item)
        except:
            pass

    df_foods = pd.DataFrame(food_db)
    for nk in nutrient_keys:
        if nk in df_foods.columns:
            df_foods[nk] = pd.to_numeric(df_foods[nk], errors='coerce')

    food_median = df_foods.groupby('name')[nutrient_keys].median().reset_index()
    food_median = food_median.dropna(subset=['calories'])
    food_median = food_median.sort_values('name')

    print(f'  Total food item records: {len(df_foods)}')
    print(f'  Unique foods: {len(food_median)}')
    print(f'\n  Sample foods:')
    print(food_median[['name', 'calories', 'protein', 'sodium', 'potassium', 'phosphorus']].head(20).to_string(index=False))
else:
    print(f'  WARNING: {backfill_path} not found — skipping food database')
    food_median = pd.DataFrame(columns=['name'] + nutrient_keys)

# ═══════════════════════════════════════════════════════════
# CELL 11: Food-Based What-If
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 11: Food-based what-if prediction...')
print('─' * 70)

def food_whatif(food_list, food_db=None):
    if food_db is None:
        food_db = food_median
    matched = []
    for food_name in food_list:
        mask = food_db['name'].str.contains(food_name.lower(), case=False, na=False)
        hits = food_db[mask]
        if len(hits) > 0:
            matched.append(hits.iloc[0])
        else:
            print(f"  Warning: '{food_name}' not found in database")

    if not matched:
        print('No foods matched!')
        return None, None, None

    df_matched = pd.DataFrame(matched)
    totals = df_matched[nutrient_keys].sum()
    scenario = {k: totals[k] for k in nutrient_keys if pd.notna(totals.get(k, np.nan))}

    print(f"\n{'='*60}")
    print(f"  FOOD WHAT-IF: {len(matched)} items")
    print(f"{'='*60}")
    print(f"\n  Foods matched:")
    for _, row in df_matched.iterrows():
        print(f"    * {row['name']}: {row['calories']:.0f} cal, {row['protein']:.1f}g protein")
    print(f"\n  Daily Totals:")
    print(f"    Calories:    {totals['calories']:.0f} kcal")
    print(f"    Protein:     {totals['protein']:.1f} g")
    print(f"    Sodium:      {totals['sodium']:.0f} mg")
    print(f"    Potassium:   {totals['potassium']:.0f} mg")
    print(f"    Phosphorus:  {totals['phosphorus']:.0f} mg")

    limits = {'sodium': 2000, 'potassium': 2000, 'phosphorus': 800}
    for nutrient, limit in limits.items():
        val = totals.get(nutrient, 0)
        if val > limit:
            print(f"    WARNING: {nutrient.title()} ({val:.0f}) EXCEEDS limit ({limit} mg)!")

    results = predict_whatif(scenario)
    return totals.to_dict(), results, df_matched

if len(food_median) > 0:
    my_foods = ['white rice', 'grilled chicken', 'banana', 'white bread', 'egg']
    totals, results, matched = food_whatif(my_foods)
else:
    print('  Skipping food what-if (no food database)')

# ═══════════════════════════════════════════════════════════
# CELL 12: Overlay What-If on Historical Wellness Timeline
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 12: Historical wellness overlay...')
print('─' * 70)

hist_ws = df_wellness['W_product'].dropna()
hist_smoothed = hist_ws.rolling('14D', center=True).mean()

optimal = predict_whatif({
    'calories': 2100, 'protein': 60, 'sodium': 1500, 'potassium': 1200,
    'phosphorus': 600, 'sessions_7d': 4, 'active_days_7d': 5,
}, verbose=False)

worst = predict_whatif({
    'calories': 3500, 'protein': 20, 'sodium': 4000, 'potassium': 4000,
    'phosphorus': 1500, 'sessions_7d': 1, 'active_days_7d': 1,
}, verbose=False)

fig, ax = plt.subplots(figsize=(18, 7))
ax.plot(hist_ws.index, hist_ws.values, '.', color='#90CAF9', alpha=0.3, markersize=3)
ax.plot(hist_smoothed.index, hist_smoothed.values, '-', color='#2196F3', linewidth=2, label='Historical (14d smoothed)')

future_start = hist_ws.index.max() + timedelta(days=1)
ax.axhspan(optimal['holistic_score'] - 3, optimal['holistic_score'] + 3,
           xmin=0.9, xmax=1.0, alpha=0.3, color='green', label=f'Optimal scenario ({optimal["holistic_score"]:.0f})')
ax.axhspan(worst['holistic_score'] - 3, worst['holistic_score'] + 3,
           xmin=0.9, xmax=1.0, alpha=0.3, color='red', label=f'Worst case ({worst["holistic_score"]:.0f})')

ax.plot(future_start, optimal['holistic_score'], 'g^', markersize=15, markeredgecolor='darkgreen', zorder=5)
ax.plot(future_start, worst['holistic_score'], 'rv', markersize=15, markeredgecolor='darkred', zorder=5)

ax.axhline(75, color='green', linestyle='--', alpha=0.3)
ax.axhline(50, color='red', linestyle='--', alpha=0.3)
ax.set_ylabel('Wellness Score (0-100)')
ax.set_title('Historical Wellness + What-If Projection', fontweight='bold', fontsize=14)
ax.legend(loc='lower left', fontsize=9)
ax.set_ylim(0, 105)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

plt.tight_layout()
plt.savefig(FEATURES_DIR / 'whatif_historical_overlay.png', dpi=150, bbox_inches='tight')
plt.close()
print('  Saved: whatif_historical_overlay.png')

# ═══════════════════════════════════════════════════════════
# CELL 13: Export What-If Parameters for MATLAB/Simulink
# ═══════════════════════════════════════════════════════════
print('\n' + '─' * 70)
print('  CELL 13: MATLAB/Simulink export...')
print('─' * 70)

try:
    import scipy.io as sio

    last_step = list(holistic_model['pipeline'].named_steps.keys())[-1]
    estimator = holistic_model['pipeline'].named_steps[last_step]
    feat_imp = estimator.feature_importances_ if hasattr(estimator, 'feature_importances_') else np.zeros(len(FEATURE_NAMES))

    matlab_export = {
        'feature_names': np.array(FEATURE_NAMES, dtype=object),
        'baseline_vector': np.array([BASELINE[f] for f in FEATURE_NAMES]),
        'feature_importances': feat_imp,
        'sweep_potassium_values': sweep_results['potassium']['values'],
        'sweep_potassium_scores': np.array(sweep_results['potassium']['scores']),
        'sweep_sodium_values': sweep_results['sodium']['values'],
        'sweep_sodium_scores': np.array(sweep_results['sodium']['scores']),
        'sweep_blood_flow_values': sweep_results['blood_flow']['values'],
        'sweep_blood_flow_scores': np.array(sweep_results['blood_flow']['scores']),
        'heatmap_bathK': bath_k_range,
        'heatmap_bathCa': bath_ca_range,
        'heatmap_health': heatmap_health,
        'heatmap_hypoK': heatmap_hypoK,
        'heatmap_hyperK': heatmap_hyperK,
        'scenario_names': np.array(list(scenarios.keys()), dtype=object),
        'scenario_scores': comp_df['holistic_score'].values,
        'hist_wellness_dates': np.array([d.toordinal() for d in hist_ws.index]),
        'hist_wellness_values': hist_ws.values,
        'esrd_limits': np.array([
            [1800, 2500], [50, 70], [0, 2000], [0, 2000], [0, 800],
            [350, 450], [1.5, 2.5], [2.0, 3.0], [180, 270],
        ]),
        'esrd_limit_names': np.array(['calories', 'protein', 'sodium', 'potassium',
                                      'phosphorus', 'blood_flow', 'bath_k', 'bath_ca',
                                      'session_duration'], dtype=object),
    }

    mat_path = PROJECT_ROOT.parent / 'HEBCSL_MATLAB' / 'results' / 'S07_whatif_data.mat'
    mat_path.parent.mkdir(parents=True, exist_ok=True)
    sio.savemat(str(mat_path), matlab_export)
    print(f'  Exported: {mat_path}')
    print(f'  Keys: {list(matlab_export.keys())}')
    print(f'  Feature importances shape: {feat_imp.shape}')
    print(f'  Baseline vector shape: {matlab_export["baseline_vector"].shape}')
except Exception as e:
    print(f'  MATLAB export skipped: {e}')

# ═══════════════════════════════════════════════════════════
# CELL 14: Summary
# ═══════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('   NB07 WHAT-IF CLINICAL SIMULATOR — COMPLETE')
print('=' * 70)
print(f'''
  Models loaded:
    * Holistic health: GradientBoosting, R2={holistic_model["metrics"]["R²"]:.3f}
    * Risk models: {len(RISK_MODELS)} classifiers
    * HEBCS pathways: {len(PATHWAY_DEFS)}

  Capabilities:
    1. Single-scenario prediction (Cell 3)
    2. Multi-scenario comparison (Cell 4-5)
    3. Sensitivity sweeps — {len(SWEEP_VARS)} variables (Cell 6-7)
    4. Multi-day trajectory simulation (Cell 8)
    5. Dialysate composition 2D heatmap (Cell 9)
    6. Food item lookup & prediction (Cell 10-11)
    7. Historical overlay (Cell 12)

  Artifacts saved:
    * whatif_scenario_comparison.png
    * whatif_sensitivity_sweeps.png
    * whatif_sensitivity_enhanced.png
    * whatif_scenario_log.png
    * whatif_dialysate_heatmap.png
    * whatif_dialysate_lognorm.png
    * whatif_trajectory_14d.png
    * whatif_trajectory_symlog.png
    * whatif_historical_overlay.png
''')
