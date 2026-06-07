"""
Generate IEEE J-BHI Graphical Abstract — HEBCS Framework Architecture
=====================================================================
Produces a single-image summary of the HEBCS pipeline for the
IEEE J-BHI submission graphical abstract.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(12, 5), dpi=300)
ax.set_xlim(0, 12)
ax.set_ylim(0, 5)
ax.axis("off")

# ── Color palette ──
colors = {
    "data":    "#2196F3",   # blue
    "bridge":  "#4CAF50",   # green
    "score":   "#FF9800",   # orange
    "ml":      "#9C27B0",   # purple
    "drift":   "#F44336",   # red
    "whatif":  "#00BCD4",   # teal
    "json":    "#FFC107",   # amber
}

# ── Box positions (x, y, w, h) ──
boxes = [
    ("Data\nSources",        0.3, 1.8, 1.5, 1.4, colors["data"]),
    ("Feature\nBridge",      2.3, 1.8, 1.5, 1.4, colors["bridge"]),
    ("Scoring\nEngine",      4.3, 1.8, 1.5, 1.4, colors["score"]),
    ("ML Risk\nPipeline",    6.3, 1.8, 1.5, 1.4, colors["ml"]),
    ("Drift\nMonitor",       8.3, 1.8, 1.5, 1.4, colors["drift"]),
    ("What-If\nSimulator",  10.3, 1.8, 1.5, 1.4, colors["whatif"]),
]

# ── Draw boxes ──
for label, x, y, w, h, color in boxes:
    fancy = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.1",
        facecolor=color, edgecolor="white",
        linewidth=2, alpha=0.9
    )
    ax.add_patch(fancy)
    ax.text(x + w/2, y + h/2, label,
            ha="center", va="center",
            fontsize=10, fontweight="bold", color="white")

# ── Arrows between boxes ──
arrow_y = 2.5
for i in range(5):
    x_start = boxes[i][1] + boxes[i][3]
    x_end = boxes[i+1][1]
    ax.annotate("", xy=(x_end, arrow_y), xytext=(x_start, arrow_y),
                arrowprops=dict(arrowstyle="->,head_width=0.3,head_length=0.15",
                                color="#333333", lw=2))

# ── Sub-labels below boxes ──
sublabels = [
    "Labs, Devices,\nNutrition, Symptoms",
    "284 daily /\n141 session features",
    "Trapezoidal MF\n7 EBC pathways",
    "5 algorithms\n11 models",
    "OOR, missing,\nextreme shift",
    "Sensitivity sweeps\nSimulink/Stateflow",
]
for i, (label, x, y, w, h, color) in enumerate(boxes):
    ax.text(x + w/2, y - 0.3, sublabels[i],
            ha="center", va="top",
            fontsize=6.5, color="#555555", style="italic")

# ── JSON config callout ──
json_x, json_y = 5.05, 3.7
json_box = FancyBboxPatch(
    (json_x - 0.7, json_y - 0.25), 1.4, 0.5,
    boxstyle="round,pad=0.08",
    facecolor=colors["json"], edgecolor="#E0A800",
    linewidth=1.5, alpha=0.95
)
ax.add_patch(json_box)
ax.text(json_x, json_y, "pathways.json",
        ha="center", va="center",
        fontsize=8, fontweight="bold", color="#333",
        family="monospace")
ax.annotate("", xy=(5.05, 3.2), xytext=(5.05, json_y - 0.25),
            arrowprops=dict(arrowstyle="->,head_width=0.2,head_length=0.1",
                            color="#E0A800", lw=1.5))

# ── Title ──
ax.text(6.0, 4.6,
        "HEBCS: Multi-Pathway Composite Scoring Framework",
        ha="center", va="center",
        fontsize=14, fontweight="bold", color="#222222")

# ── Key result callout ──
result_text = (
    "Validated: 9.8 yr ESRD  |  "
    "10/10 classifiers AUC ≥ 0.84  |  "
    "Python–MATLAB r = 1.0000  |  "
    "Disease-agnostic via JSON config"
)
ax.text(6.0, 0.5, result_text,
        ha="center", va="center",
        fontsize=8, color="#333333",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#F5F5F5",
                  edgecolor="#CCCCCC", linewidth=1))

# ── Multiplicative formula ──
ax.text(6.0, 4.15,
        r"$W = 100 \times \prod_{p} O_p^{w_p}$   (non-compensable aggregation)",
        ha="center", va="center",
        fontsize=9, color="#666666", style="italic")

plt.tight_layout()
out = "docs/latex/figures/graphical_abstract.png"
fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
print(f"Saved: {out}")
plt.close()
