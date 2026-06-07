#!/usr/bin/env python3
"""
Clinical Milestones Figure — 5-panel visualization showing:
  1. G6PD diagnosis (Oct 2018) — treatment protocol revolution
  2. Parathyroidectomy (Mar 2025) — PTH resolution

Data sources:
  - EHR labs (records_lab.csv): full hemoglobin timeline 2016-2024
  - API labs: 2025+ data
  - Unified labs: PTH, Ferritin, iron studies
  - Flowsheet sessions: Epogen/Venofer dosing, BP
  - Wellness daily: pathway scores (index=date, pathway_* columns)
"""
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "features"

# ── Clinical milestones ──────────────────────────────────
G6PD = pd.Timestamp("2018-10-01")
SURGERY = pd.Timestamp("2019-01-15")
PTX = pd.Timestamp("2025-03-01")

# ── Colors ───────────────────────────────────────────────
C_G6PD = "#E74C3C"
C_PTX = "#8E44AD"
C_SURG = "#FF9800"

pathway_colors = {
    "pathway_Metabolic": ("#E74C3C", "Metabolic"),
    "pathway_Digestive_Enhanced": ("#2ECC71", "Digestive"),
    "pathway_Neurological_Enhanced": ("#34495E", "Neurological"),
    "pathway_Hemolytical": ("#C0392B", "Hemolytical"),
    "pathway_Endocrinology": ("#3498DB", "Endocrinology"), 
    "pathway_Bone_Formation": ("#F39C12", "Bone Formation"),
    "pathway_Immunological": ("#9B59B6", "Immunological"),
    "pathway_GI_Function": ("#1ABC9C", "GI Function"),
    "pathway_Nutrition": ("#E67E22", "Nutrition"),
}

# ── Helper functions ─────────────────────────────────────
def add_milestones(ax):
    ax.axvline(G6PD, color=C_G6PD, ls="--", lw=1.5, alpha=0.8, zorder=5)
    ax.axvline(PTX, color=C_PTX, ls="--", lw=1.5, alpha=0.8, zorder=5)

def add_eras(ax):
    ylim = ax.get_ylim()
    ax.axvspan(mdates.date2num(pd.Timestamp("2016-01-01")), mdates.date2num(G6PD),
               alpha=0.06, color="#FF9800", zorder=0)
    ax.axvspan(mdates.date2num(G6PD), mdates.date2num(PTX),
               alpha=0.06, color="#4CAF50", zorder=0)
    ax.axvspan(mdates.date2num(PTX), mdates.date2num(pd.Timestamp("2026-12-31")),
               alpha=0.06, color="#673AB7", zorder=0)
    ax.set_ylim(ylim)

# ══════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════
print("Loading data...")

# 1. EHR labs (full hemoglobin timeline)
ehr = pd.read_csv(BASE / "data" / "raw" / "excel" / "records_lab.csv", low_memory=False)
ehr["date"] = pd.to_datetime(ehr["date"], errors="coerce")
ehr["value_numeric"] = pd.to_numeric(ehr["value_numeric"], errors="coerce")

# 2. API labs (2025+)
api = pd.read_csv(BASE / "data" / "raw" / "api" / "lab_results.csv")
api["date"] = pd.to_datetime(api["date"], errors="coerce")
api["value_numeric"] = pd.to_numeric(api["value"], errors="coerce")

# 3. Unified labs (for PTH full timeline)
uni = pd.read_csv(BASE / "data" / "processed" / "unified_labs.csv", low_memory=False)
uni["date"] = pd.to_datetime(uni["date"], errors="coerce")
uni["value_numeric"] = pd.to_numeric(uni["value_numeric"], errors="coerce")

# 4. Daily unified (BP)
daily = pd.read_csv(BASE / "data" / "processed" / "daily_unified.csv", parse_dates=["date"])

# 5. Wellness (pathway scores) — index column is date
wellness = pd.read_csv(BASE / "data" / "features" / "HEBCS_wellness_daily.csv", index_col=0)
wellness.index = pd.to_datetime(wellness.index, errors="coerce")
wellness.index.name = "date"
wellness = wellness.reset_index()

# 6. Flowsheet sessions (Epogen/Venofer)
flows = pd.read_csv(BASE / "data" / "raw" / "excel" / "all_flowsheet_sessions.csv", low_memory=False)
flows["session_date"] = pd.to_datetime(flows["session_date"], errors="coerce")

print(f"EHR labs: {len(ehr)}, API labs: {len(api)}, Unified: {len(uni)}")
print(f"Daily unified: {daily.shape}, Wellness: {wellness.shape}")
print(f"Flowsheet sessions: {len(flows)}")

# ══════════════════════════════════════════════════════════
# EXTRACT SERIES
# ══════════════════════════════════════════════════════════

# Hemoglobin — combine EHR + API, filter 2-20 g/dL
hgb_ehr = ehr[ehr["test_name"].str.contains("^Hemoglobin$|^HGB$", case=False, na=False, regex=True)].copy()
hgb_api = api[api["test_name"].str.contains("^Hemoglobin$|^HGB$", case=False, na=False, regex=True)].copy()
hgb = pd.concat([
    hgb_ehr[["date", "value_numeric"]],
    hgb_api[["date", "value_numeric"]]
]).dropna().drop_duplicates()
hgb = hgb[(hgb["value_numeric"] >= 2) & (hgb["value_numeric"] <= 20)].sort_values("date").reset_index(drop=True)
hgb.columns = ["date", "hgb"]
print(f"Clean hemoglobin: {len(hgb)} ({hgb['date'].min().date()} -> {hgb['date'].max().date()})")

# PTH — from unified labs (fullest)
pth = uni[uni["test_name"].str.contains("PTH|parathyroid", case=False, na=False)].copy()
pth = pth[["date", "value_numeric"]].dropna().sort_values("date").reset_index(drop=True)
pth.columns = ["date", "pth"]
pth = pth[(pth["pth"] > 0) & (pth["pth"] < 20000)]
print(f"PTH: {len(pth)} ({pth['date'].min().date()} -> {pth['date'].max().date()})")

# Epogen dosing from flowsheet medications column
def parse_epogen(med_str):
    if pd.isna(med_str):
        return np.nan, np.nan
    epo_dose = np.nan
    veno_dose = np.nan
    for part in str(med_str).split(";"):
        part = part.strip().lower()
        if "epogen" in part and "none" not in part:
            val = part.split("=")[1] if "=" in part else ""
            val = val.replace(",", "").replace("sq", "").replace("weekly", "").strip()
            try:
                epo_dose = float(val)
            except:
                pass
        if "venofer" in part:
            val = part.split("=")[1] if "=" in part else ""
            val = val.replace(",", "").replace("mg", "").strip()
            try:
                veno_dose = float(val)
            except:
                pass
    return epo_dose, veno_dose

epo_veno = flows[["session_date", "medications"]].dropna(subset=["medications"]).copy()
parsed = epo_veno["medications"].apply(parse_epogen)
epo_veno["epogen"] = parsed.apply(lambda x: x[0])
epo_veno["venofer"] = parsed.apply(lambda x: x[1])
epo_data = epo_veno[["session_date", "epogen"]].dropna().sort_values("session_date")
veno_data = epo_veno[["session_date", "venofer"]].dropna().sort_values("session_date")
print(f"Epogen doses: {len(epo_data)}, Venofer doses: {len(veno_data)}")

# ══════════════════════════════════════════════════════════
# FIGURE: 5 panels
# ══════════════════════════════════════════════════════════
fig, axes = plt.subplots(5, 1, figsize=(16, 24), sharex=True,
                         gridspec_kw={"hspace": 0.18})

# ── PANEL A: Hemoglobin + transfusion markers + Hgb<8 zones ──
ax = axes[0]

ax.plot(hgb["date"], hgb["hgb"], ".-", color="#2196F3", alpha=0.35, ms=3, lw=0.8)
hgb_roll = hgb.set_index("date")["hgb"].rolling("90D", min_periods=5).mean()
ax.plot(hgb_roll.index, hgb_roll.values, "-", color="#1565C0", lw=2.5, label="Hemoglobin (90d mean)")

# Variability on twin axis
hgb_std = hgb.set_index("date")["hgb"].rolling("90D", min_periods=5).std()
ax2 = ax.twinx()
ax2.fill_between(hgb_std.index, 0, hgb_std.values, alpha=0.12, color="#FF5722")
ax2.plot(hgb_std.index, hgb_std.values, "-", color="#FF5722", lw=1, alpha=0.5)
ax2.set_ylabel("Variability (90d std)", fontsize=9, color="#FF5722")
ax2.set_ylim(0, 3.5)
ax2.tick_params(axis='y', labelcolor="#FF5722", labelsize=8)

# Transfusion proxies
hgb_diff = hgb["hgb"].diff()
transfusions = hgb[hgb_diff > 2.0]
ax.scatter(transfusions["date"], transfusions["hgb"],
           marker="^", s=100, c="#D32F2F", zorder=10, edgecolors="white", linewidths=1,
           label=f"Probable transfusion (n={len(transfusions)})")

# Critical zone and target
ax.axhspan(0, 8, alpha=0.06, color="#F44336")
ax.axhspan(10, 13, alpha=0.08, color="#4CAF50")
ax.text(pd.Timestamp("2024-01-01"), 6.5, "<8 g/dL zone", fontsize=8, color="#D32F2F", alpha=0.8)
ax.text(pd.Timestamp("2024-01-01"), 12.5, "ESRD target\n(10-13)", fontsize=7, color="#388E3C", alpha=0.7)

# Surgery annotation
ax.annotate("Surgery\n01/2019",
            xy=(mdates.date2num(SURGERY), 5.4),
            xytext=(mdates.date2num(pd.Timestamp("2019-08-01")), 4.5),
            fontsize=8, color=C_SURG, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=C_SURG, lw=1.2))

# Stats annotations
pre_lt8 = (hgb[hgb["date"] < G6PD]["hgb"] < 8).mean() * 100
post_lt8 = (hgb[hgb["date"] >= pd.Timestamp("2019-07-01")]["hgb"] < 8).mean() * 100
ax.text(0.98, 0.95, f"Hgb <8: {pre_lt8:.0f}% pre-G6PD  vs  {post_lt8:.0f}% post-adj",
        transform=ax.transAxes, fontsize=9, ha="right", va="top",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#1565C0", alpha=0.9))

add_milestones(ax)
ax.set_ylabel("Hemoglobin (g/dL)", fontsize=11)
ax.set_title("A) Hemoglobin Trajectory — G6PD-Driven Self-Management Eliminates Transfusion Dependency",
             fontsize=12, fontweight="bold", loc="left")
ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
ax.set_ylim(4, 15)
add_eras(ax)

# ── PANEL B: Epogen dosing shift + Venofer introduction ──
ax = axes[1]

# Epogen doses
if len(epo_data) > 0:
    ax.scatter(epo_data["session_date"], epo_data["epogen"], s=15, alpha=0.4,
               color="#1565C0", zorder=3, label="Epogen dose (IU)")
    epo_roll = epo_data.set_index("session_date")["epogen"].rolling("90D", min_periods=5).mean()
    ax.plot(epo_roll.index, epo_roll.values, "-", color="#0D47A1", lw=2.5, label="Epogen (90d mean)")

# Venofer on twin axis
if len(veno_data) > 0:
    ax3 = ax.twinx()
    ax3.scatter(veno_data["session_date"], veno_data["venofer"], s=20, alpha=0.5,
                color="#E65100", marker="s", zorder=3, label="Venofer dose (mg)")
    veno_roll = veno_data.set_index("session_date")["venofer"].rolling("90D", min_periods=3).mean()
    ax3.plot(veno_roll.index, veno_roll.values, "-", color="#BF360C", lw=2, label="Venofer (90d mean)")
    ax3.set_ylabel("Venofer (mg)", fontsize=10, color="#BF360C")
    ax3.tick_params(axis='y', labelcolor="#BF360C")
    ax3.legend(loc="upper right", fontsize=8, framealpha=0.9)

# Annotation: protocol shift
ax.annotate("Self-administered\ncontinuous ESA/iron\nprotocol begins",
            xy=(mdates.date2num(pd.Timestamp("2019-03-01")), 10000),
            xytext=(mdates.date2num(pd.Timestamp("2020-06-01")), 18000),
            fontsize=8, color=C_G6PD, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=C_G6PD, lw=1.2),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=C_G6PD, alpha=0.9))

add_milestones(ax)
ax.set_ylabel("Epogen (IU)", fontsize=11)
ax.set_title("B) ESA & Iron Protocol — High-Dose Quarterly to Low-Dose Continuous Self-Administration",
             fontsize=12, fontweight="bold", loc="left")
ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
add_eras(ax)

# ── PANEL C: Blood Pressure trajectory ──────────────────
ax = axes[2]

bp_cols_pre = [c for c in daily.columns if "pre_bp" in c.lower() and "sys" in c.lower()]
bp_cols_post = [c for c in daily.columns if "post_bp" in c.lower() and "sys" in c.lower()]

if bp_cols_pre:
    bp_pre_col = bp_cols_pre[0]
    bp_data = daily[["date", bp_pre_col]].dropna().copy()
    bp_data.columns = ["date", "systolic"]
    ax.plot(bp_data["date"], bp_data["systolic"], ".", color="#607D8B", alpha=0.12, ms=2)
    bp_roll = bp_data.set_index("date")["systolic"].rolling("60D", min_periods=10).mean()
    ax.plot(bp_roll.index, bp_roll.values, "-", color="#1B5E20", lw=2.5, label="Pre-dialysis systolic (60d mean)")

if bp_cols_post:
    bp_post_col = bp_cols_post[0]
    bp_data2 = daily[["date", bp_post_col]].dropna().copy()
    bp_data2.columns = ["date", "systolic"]
    bp_roll2 = bp_data2.set_index("date")["systolic"].rolling("60D", min_periods=10).mean()
    ax.plot(bp_roll2.index, bp_roll2.values, "-", color="#E65100", lw=2, alpha=0.8, label="Post-dialysis systolic (60d mean)")

ax.axhspan(140, 200, alpha=0.06, color="#F44336")
ax.axhspan(0, 90, alpha=0.06, color="#2196F3")
ax.text(pd.Timestamp("2024-01-01"), 160, "Hypertension", fontsize=8, color="#D32F2F", alpha=0.8)
ax.text(pd.Timestamp("2024-01-01"), 78, "Hypotension", fontsize=8, color="#1565C0", alpha=0.8)

ax.annotate("Amlodipine & Labetalol\neliminated (from EHR)",
            xy=(mdates.date2num(pd.Timestamp("2019-01-15")), 140),
            xytext=(mdates.date2num(pd.Timestamp("2020-03-01")), 175),
            fontsize=8, color=C_G6PD,
            arrowprops=dict(arrowstyle="->", color=C_G6PD, lw=1.2),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=C_G6PD, alpha=0.9))

add_milestones(ax)
ax.set_ylabel("Systolic BP (mmHg)", fontsize=11)
ax.set_title("C) Blood Pressure — Hypertension to Hypotension Shift After Antihypertensive Elimination",
             fontsize=12, fontweight="bold", loc="left")
ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
ax.set_ylim(60, 200)
add_eras(ax)

# ── PANEL D: PTH trajectory with parathyroidectomy ──────
ax = axes[3]

ax.plot(pth["date"], pth["pth"], "o-", color="#7B1FA2", ms=4, lw=1.2, alpha=0.7, label="PTH (pg/mL)")
ax.axhspan(150, 600, alpha=0.08, color="#4CAF50")
ax.text(pd.Timestamp("2016-06-01"), 450, "KDOQI target\n(150-600)", fontsize=8, color="#388E3C", alpha=0.7)

ax.annotate("Parathyroidectomy\n03/2025\nPTH: 8,478 -> 14",
            xy=(mdates.date2num(PTX), 14),
            xytext=(mdates.date2num(pd.Timestamp("2023-01-01")), 5000),
            fontsize=10, fontweight="bold", color=C_PTX,
            arrowprops=dict(arrowstyle="->", color=C_PTX, lw=2),
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#EDE7F6", edgecolor=C_PTX, alpha=0.9))

# Show the escalation trajectory
ax.annotate("Progressive secondary\nhyperparathyroidism\n(9 years unresolved)",
            xy=(mdates.date2num(pd.Timestamp("2022-01-01")), 3300),
            xytext=(mdates.date2num(pd.Timestamp("2019-06-01")), 7000),
            fontsize=8, color="#4A148C",
            arrowprops=dict(arrowstyle="->", color="#4A148C", lw=1))

add_milestones(ax)
ax.set_ylabel("PTH (pg/mL)", fontsize=11)
ax.set_title("D) Parathyroid Hormone — 9-Year Escalation to Surgical Resolution",
             fontsize=12, fontweight="bold", loc="left")
ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
add_eras(ax)

# ── PANEL E: Pathway scores (rolling 90d mean) ──────────
ax = axes[4]

for pw_col, (color, label) in pathway_colors.items():
    if pw_col in wellness.columns:
        valid = wellness[["date", pw_col]].dropna()
        if len(valid) > 10:
            roll = valid.set_index("date")[pw_col].rolling("90D", min_periods=10).mean()
            ax.plot(roll.index, roll.values, "-", color=color, lw=2, alpha=0.85, label=label)

# Composite score on twin axis
if "W_product" in wellness.columns:
    ax4 = ax.twinx()
    valid = wellness[["date", "W_product"]].dropna()
    roll_prod = valid.set_index("date")["W_product"].rolling("90D", min_periods=10).mean()
    ax4.plot(roll_prod.index, roll_prod.values, "-", color="#0D47A1", lw=3, alpha=0.4, label="W_product (90d)")
    ax4.set_ylabel("Composite Score", fontsize=9, color="#0D47A1")
    ax4.tick_params(axis='y', labelcolor="#0D47A1", labelsize=8)
    ax4.set_ylim(-5, 110)

add_milestones(ax)
ax.set_ylabel("Pathway Score (0-1)", fontsize=11)
ax.set_title("E) HEBCS Pathway Scores — Hemolytical Improvement, Endocrine/Bone Decline",
             fontsize=12, fontweight="bold", loc="left")
ax.legend(loc="lower left", fontsize=7, ncol=3, framealpha=0.9)
ax.set_ylim(0, 1.05)
add_eras(ax)

# ── X-axis formatting ───────────────────────────────────
axes[-1].xaxis.set_major_locator(mdates.YearLocator())
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
axes[-1].set_xlabel("Year", fontsize=12)

# ── Global legend ────────────────────────────────────────
legend_els = [
    Line2D([0], [0], color=C_G6PD, ls="--", lw=1.5, label="G6PD Diagnosis (Oct 2018)"),
    Line2D([0], [0], color=C_PTX, ls="--", lw=1.5, label="Parathyroidectomy (Mar 2025)"),
]
fig.legend(handles=legend_els, loc="upper center", ncol=2, fontsize=11,
           framealpha=0.95, edgecolor="#ccc", bbox_to_anchor=(0.5, 0.997))

fig.suptitle("Clinical Milestones in HEBCS: G6PD Diagnosis & Parathyroidectomy",
             fontsize=16, fontweight="bold", y=1.01)

plt.tight_layout(rect=[0, 0, 1, 0.98])
outpath = OUT / "clinical_milestones_panel.png"
fig.savefig(outpath, dpi=200, bbox_inches="tight", facecolor="white")
print(f"\nSaved: {outpath}")
print(f"Size: {outpath.stat().st_size / 1e6:.1f} MB")
plt.close()

print("\n=== DONE ===")
