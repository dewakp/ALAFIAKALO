#!/usr/bin/env python3
"""Extract NB05 hypothesis test numbers for paper update."""
import pandas as pd, numpy as np
from pathlib import Path
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.model_selection import cross_val_score
from scipy import stats

F = Path(__file__).resolve().parent.parent / 'data' / 'features'
w = pd.read_csv(F / 'HEBCS_wellness_daily.csv', index_col=0, parse_dates=True)
ps = pd.read_csv(F / 'HEBCS_pathway_scores.csv')

# Pivot pathways
piv = ps.pivot(index='date', columns='pathway', values='score').dropna()
print('=== PATHWAY CORRELATION ===')
corr = piv.corr()
mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
upper = corr.where(mask)
vals = upper.stack().values
print(f'  Mean |r|: {np.abs(vals).mean():.3f}')
print(f'  Max  |r|: {np.abs(vals).max():.3f}')
print(f'  Min  |r|: {np.abs(vals).min():.3f}')

# PCA
pca = PCA().fit(piv)
cumvar = np.cumsum(pca.explained_variance_ratio_)
n90 = int(np.searchsorted(cumvar, 0.90) + 1)
print(f'  PCs for 90% variance: {n90}')
print(f'  PC1 variance: {pca.explained_variance_ratio_[0]*100:.1f}%')

# H2: Product vs additive
wp = w['W_product'].dropna()
wa = w['W_additive'].dropna()
common = wp.index.intersection(wa.index)
wp_c = wp.loc[common]
wa_c = wa.loc[common]
t_stat, p_val = stats.ttest_rel(wp_c, wa_c)
print(f'\n=== H2: PRODUCT vs ADDITIVE ===')
print(f'  paired t = {t_stat:.1f}, p = {p_val:.2e}')

# H3: Variance differs
F_stat, F_p = stats.levene(wp_c, wa_c)
print(f'\n=== H3: VARIANCE DIFFERS ===')
print(f'  Levene F = {F_stat:.1f}, p = {F_p:.2e}')
print(f'  Product std = {wp_c.std():.4f}')
print(f'  Additive std = {wa_c.std():.4f}')

# H4: Autocorrelation
lag1 = wp_c.autocorr(lag=1)
print(f'\n=== H4: AUTOCORRELATION ===')
print(f'  Lag-1 autocorr: {lag1:.3f}')

# H5: Multi-pathway vs single
piv.index = pd.to_datetime(piv.index)
common2 = piv.index.intersection(wp.index)
X_multi = piv.loc[common2].values
y = wp.loc[common2].values

r2_multi = cross_val_score(Ridge(), X_multi, y, cv=5, scoring='r2').mean()
print(f'\n=== H5: MULTI vs SINGLE PATHWAY ===')
print(f'  Multi-pathway R2 (5-fold): {r2_multi:.3f}')
best_single = 0
best_name = ''
for i, p_name in enumerate(piv.columns):
    X_single = X_multi[:, i:i+1]
    r2_s = cross_val_score(Ridge(), X_single, y, cv=5, scoring='r2').mean()
    print(f'  {p_name}: R2 = {r2_s:.3f}')
    if r2_s > best_single:
        best_single = r2_s
        best_name = p_name
print(f'\n  Best single: {best_name} R2={best_single:.3f}')
print(f'  Multi-pathway advantage: {(r2_multi - best_single)*100:.1f} pp')
