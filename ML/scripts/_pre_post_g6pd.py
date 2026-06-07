"""
Pre/Post G6PD Diagnosis Analysis
Inflection point: October 2018 (G6PD discovery)
Secondary milestone: January 2019 (treatment adjustments fully in place)

Clinical changes to verify:
1. Hemoglobin stability (less fluctuation post-G6PD)
2. Blood transfusion frequency (quarterly pre-10/2018, none post-06/2019)
3. Hypertension elimination post-01/2019 (but increased hypotension)
4. Less intradialytic vomiting post-2019
5. Venofer (iron) administration post-10/2018
"""
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy import stats

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "features"

# Load data
daily = pd.read_csv(BASE / "data" / "processed" / "daily_unified.csv", parse_dates=["date"])
print(f"Daily unified: {daily.shape}")
print(f"Columns sample: {list(daily.columns[:30])}")

# Define periods
G6PD_DATE = pd.Timestamp("2018-10-01")
FULL_ADJ  = pd.Timestamp("2019-01-01")
TRANSFUSION_END = pd.Timestamp("2019-06-01")

pre  = daily[daily["date"] < G6PD_DATE]
post = daily[daily["date"] >= FULL_ADJ]
print(f"\nPre-G6PD (before 10/2018): {len(pre)} days")
print(f"Post-adjustment (after 01/2019): {len(post)} days")

# ---- 1. HEMOGLOBIN STABILITY ----
print("\n" + "="*60)
print("1. HEMOGLOBIN STABILITY")
print("="*60)

hgb_cols = [c for c in daily.columns if "hemoglobin" in c.lower() or "HEMOGLOBIN" in c]
if not hgb_cols:
    hgb_cols = [c for c in daily.columns if "hgb" in c.lower() or "hemo" in c.lower()]
print(f"  Hemoglobin columns: {hgb_cols[:5]}")

# Try the spot value
for col in hgb_cols[:3]:
    if col in daily.columns:
        pre_vals = pre[col].dropna()
        post_vals = post[col].dropna()
        if len(pre_vals) > 5 and len(post_vals) > 5:
            # Convert to numeric if needed
            pre_vals = pd.to_numeric(pre_vals, errors="coerce").dropna()
            post_vals = pd.to_numeric(post_vals, errors="coerce").dropna()
            if len(pre_vals) > 5 and len(post_vals) > 5:
                print(f"\n  {col}:")
                print(f"    Pre:  mean={pre_vals.mean():.2f}, std={pre_vals.std():.2f}, CV={pre_vals.std()/pre_vals.mean()*100:.1f}%")
                print(f"    Post: mean={post_vals.mean():.2f}, std={post_vals.std():.2f}, CV={post_vals.std()/post_vals.mean()*100:.1f}%")
                F, p = stats.levene(pre_vals, post_vals)
                print(f"    Levene's F={F:.2f}, p={p:.2e}")

# ---- 2. BLOOD PRESSURE ----
print("\n" + "="*60)
print("2. BLOOD PRESSURE / HYPERTENSION vs HYPOTENSION")
print("="*60)

bp_cols = [c for c in daily.columns if "bp" in c.lower() or "systolic" in c.lower() or "diastolic" in c.lower() or "pressure" in c.lower() or "hypo" in c.lower() or "hyper" in c.lower()]
print(f"  BP-related columns: {bp_cols[:10]}")

for col in ["sess_pre_bp_sys", "sess_post_bp_sys", "sess_bp_lowest_sys"]:
    if col in daily.columns:
        pre_vals = pre[col].dropna()
        post_vals = post[col].dropna()
        if len(pre_vals) > 5 and len(post_vals) > 5:
            print(f"\n  {col}:")
            print(f"    Pre:  mean={pre_vals.mean():.2f}, std={pre_vals.std():.2f}, n={len(pre_vals)}")
            print(f"    Post: mean={post_vals.mean():.2f}, std={post_vals.std():.2f}, n={len(post_vals)}")

# Check hypertension (pre-systolic > 140)
if "sess_pre_bp_sys" in daily.columns:
    pre_bp = pre["sess_pre_bp_sys"].dropna()
    post_bp = post["sess_pre_bp_sys"].dropna()
    pre_hyper = (pre_bp > 140).mean() * 100
    post_hyper = (post_bp > 140).mean() * 100
    pre_hypo = (pre_bp < 100).mean() * 100
    post_hypo = (post_bp < 100).mean() * 100
    print(f"\n  Pre-dialysis SBP > 140 (hypertension):")
    print(f"    Pre:  {pre_hyper:.1f}%")
    print(f"    Post: {post_hyper:.1f}%")
    print(f"  Pre-dialysis SBP < 100 (hypotension):")
    print(f"    Pre:  {pre_hypo:.1f}%")
    print(f"    Post: {post_hypo:.1f}%")

# ---- 3. VOMITING ----
print("\n" + "="*60)
print("3. INTRADIALYTIC VOMITING")
print("="*60)

vomit_cols = [c for c in daily.columns if "vomit" in c.lower() or "nausea" in c.lower()]
if not vomit_cols:
    # Try elim columns
    vomit_cols = [c for c in daily.columns if "elim" in c.lower()]
print(f"  Vomit columns: {vomit_cols[:10]}")

# Also check for vomit in the raw processed data
vomit_file = BASE / "data" / "processed" / "vomit.csv"
if vomit_file.exists():
    vdf = pd.read_csv(vomit_file, parse_dates=["date"] if True else [0])
    # Try to detect date column
    dcol = [c for c in vdf.columns if "date" in c.lower()]
    if dcol:
        vdf["date"] = pd.to_datetime(vdf[dcol[0]])
    print(f"  Vomit CSV found: {vdf.shape}, cols: {list(vdf.columns)[:8]}")
    pre_v = vdf[vdf["date"] < G6PD_DATE]
    post_v = vdf[vdf["date"] >= FULL_ADJ]
    print(f"  Episodes pre-G6PD: {len(pre_v)}, post-adj: {len(post_v)}")
    pre_days = (G6PD_DATE - vdf["date"].min()).days
    post_days = (vdf["date"].max() - FULL_ADJ).days
    if pre_days > 0 and post_days > 0:
        pre_rate = len(pre_v) / pre_days * 365
        post_rate = len(post_v) / post_days * 365
        print(f"  Annualized rate: Pre={pre_rate:.1f}/yr  Post={post_rate:.1f}/yr")

for col in vomit_cols[:5]:
    if col in daily.columns:
        pre_vals = pre[col].dropna()
        post_vals = post[col].dropna()
        if len(pre_vals) > 5 and len(post_vals) > 5:
            print(f"\n  {col}:")
            if pre_vals.nunique() <= 3:  # binary
                print(f"    Pre:  {pre_vals.mean()*100:.1f}% positive, n={len(pre_vals)}")
                print(f"    Post: {post_vals.mean()*100:.1f}% positive, n={len(post_vals)}")
            else:
                print(f"    Pre:  mean={pre_vals.mean():.3f}, n={len(pre_vals)}")
                print(f"    Post: mean={post_vals.mean():.3f}, n={len(post_vals)}")

# ---- 4. PATHWAY SCORES PRE/POST ----
print("\n" + "="*60)
print("4. PATHWAY SCORES PRE/POST (if available)")
print("="*60)

# Check for exported HEBCS scores
wellness_csv = BASE / "data" / "features" / "HEBCS_wellness_daily.csv"
pathway_csv  = BASE / "data" / "features" / "HEBCS_pathway_scores.csv"

for fpath in [wellness_csv, pathway_csv]:
    if fpath.exists():
        print(f"\n  Found: {fpath.name}")
        wdf = pd.read_csv(fpath, parse_dates=["date"] if "date" in pd.read_csv(fpath, nrows=1).columns else [0])
        if "date" not in wdf.columns:
            wdf.rename(columns={wdf.columns[0]: "date"}, inplace=True)
        print(f"    Shape: {wdf.shape}, cols: {list(wdf.columns)}")
        
        pre_w  = wdf[wdf["date"] < G6PD_DATE]
        post_w = wdf[wdf["date"] >= FULL_ADJ]
        
        for c in wdf.select_dtypes(include=[np.number]).columns:
            if c == "date":
                continue
            pv = pre_w[c].dropna()
            qv = post_w[c].dropna()
            if len(pv) > 5 and len(qv) > 5:
                print(f"    {c:30s}  Pre: {pv.mean():.3f}±{pv.std():.3f}  Post: {qv.mean():.3f}±{qv.std():.3f}")
    else:
        print(f"  NOT FOUND: {fpath.name}")

# ---- 5. IRON (FERRITIN, ISAT) ----
print("\n" + "="*60)
print("5. IRON MARKERS (Venofer effect)")
print("="*60)

for col in ["lab_ferritin", "lab_isat", "lab_iron", "lab_ferritin_30d", "lab_isat_30d"]:
    if col in daily.columns:
        pre_vals = pre[col].dropna()
        post_vals = post[col].dropna()
        if len(pre_vals) > 2 and len(post_vals) > 2:
            print(f"  {col}:")
            print(f"    Pre:  mean={pre_vals.mean():.1f}, std={pre_vals.std():.1f}")
            print(f"    Post: mean={post_vals.mean():.1f}, std={post_vals.std():.1f}")

# ---- 6. ALL RISK FLAGS PRE/POST ----
print("\n" + "="*60)
print("6. RISK FLAGS PRE/POST")
print("="*60)

risk_cols = [c for c in daily.columns if c.startswith("risk_")]
for col in sorted(risk_cols):
    pre_vals = pre[col].dropna()
    post_vals = post[col].dropna()
    if len(pre_vals) > 10 and len(post_vals) > 10:
        pre_rate = pre_vals.mean() * 100
        post_rate = post_vals.mean() * 100
        change = post_rate - pre_rate
        marker = "↓" if change < -5 else "↑" if change > 5 else "→"
        print(f"  {col:35s}  Pre: {pre_rate:5.1f}%  Post: {post_rate:5.1f}%  {marker} ({change:+.1f}pp)")

print("\n=== DONE ===")
