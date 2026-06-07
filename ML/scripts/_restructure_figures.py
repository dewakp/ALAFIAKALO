"""
Restructure main.tex: move all figures inline, add SHAP figure.
"""
import re
from pathlib import Path

tex_path = Path(__file__).resolve().parent.parent.parent / 'docs' / 'latex' / 'main.tex'
tex = tex_path.read_text()

# ── 1. Extract all figure environments from the end-of-doc Figures section ──
# Find the Figures section
figures_section_start = tex.find('% ============================================================================\n%  FIGURES\n')
if figures_section_start == -1:
    raise ValueError("Could not find FIGURES section marker")

# Find where Supplementary Material starts (right after figures)
supp_marker = '% ============================================================================\n%  SUPPLEMENTARY MATERIAL\n'
supp_start = tex.find(supp_marker, figures_section_start)
if supp_start == -1:
    raise ValueError("Could not find SUPPLEMENTARY MATERIAL marker")

# Extract the figures block text
figures_block = tex[figures_section_start:supp_start]
print(f"Figures block: {len(figures_block)} chars")

# Remove the figures block from the document
tex = tex[:figures_section_start] + tex[supp_start:]
print("Removed end-of-doc figures block")

# ── 2. Define figure environments to insert inline ──
# All use [htbp] instead of [H] for flexible placement

fig_independence = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/pathway_independence.png}
\caption{\textbf{Inter-pathway correlation matrix, PCA scree plot, and
  pathway score distributions.}  Mean absolute $|r|=0.122$ across 21
  pairwise comparisons.  Four principal components are needed for 90\%
  variance explained.}
\label{fig:independence}
\end{figure}
"""

fig_aggregation = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/aggregation_comparison.png}
\caption{\textbf{Aggregation method comparison.}  Distributions of additive,
  product, and geometric mean wellness scores.  Product scoring exhibits
  higher variance and greater sensitivity to pathway failures.}
\label{fig:aggregation}
\end{figure}
"""

fig_predictive = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/predictive_validation.png}
\caption{\textbf{Predictive validation.}  Full multi-pathway model
  $R^{2}=0.249$ vs.\ best single pathway (all negative~$R^{2}$),
  demonstrating multi-pathway superiority.}
\label{fig:predictive}
\end{figure}
"""

fig_wellness = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/HEBCS_wellness_score.png}
\caption{\textbf{HEBCS Extended Wellness Score---10-year daily resolution.}
  Top panel: 7-day smoothed additive (blue), product (orange), and geometric
  mean (green) wellness scores with warning (50) and good (75) thresholds.
  Middle panel: individual pathway scores (14-day smoothed).
  Bottom panel: data availability timeline by pathway.}
\label{fig:wellness}
\end{figure}
"""

fig_pathways = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/pathway_scores_timeline.png}
\caption{\textbf{Individual EBC pathway score trajectories} (14-day smoothed)
  over the 10-year study period.  Hemolytical and Immunological pathways
  exhibit the greatest temporal variability.}
\label{fig:pathways}
\end{figure}
"""

fig_shap = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/shap_summary.png}
\caption{\textbf{SHAP feature importance for three clinical risk models.}
  Beeswarm plots showing the top~15 features by SHAP value magnitude for
  (left) intradialytic hypotension (RandomForest, AUC\,=\,1.000),
  (center) low hemoglobin (GradientBoosting, AUC\,=\,1.000), and
  (right) high PTH (GradientBoosting, AUC\,=\,0.999).
  Color indicates feature value (red\,=\,high, blue\,=\,low).
  HEBCS pathway scores and forward-filled laboratory values appear
  prominently among the top predictors.}
\label{fig:shap}
\end{figure}
"""

fig_sensitivity = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/whatif_sensitivity_sweeps.png}
\caption{\textbf{Sensitivity sweep plots} showing predicted health score as a
  function of 9 modifiable inputs.  Caloric intake, blood flow rate, and
  pre-dialysis SBP are the most impactful variables.}
\label{fig:sensitivity}
\end{figure}
"""

fig_sensitivity_enhanced = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/whatif_sensitivity_enhanced.png}
\caption{\textbf{Enhanced sensitivity analysis} with confidence intervals and
  nonlinear response curves for the three most impactful modifiable inputs.}
\label{fig:sensitivity_enhanced}
\end{figure}
"""

fig_heatmap = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/whatif_dialysate_heatmap.png}
\caption{\textbf{Dialysate composition heatmap}---predicted health score as a
  function of bath K\textsuperscript{+} and bath Ca\textsuperscript{2+}
  concentration.}
\label{fig:heatmap}
\end{figure}
"""

fig_trajectory = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/whatif_trajectory_14d.png}
\caption{\textbf{14-day trajectory simulation} comparing ``good week''
  (optimal inputs) vs.\ ``bad week'' (suboptimal inputs) scenarios.}
\label{fig:trajectory}
\end{figure}
"""

fig_scenarios = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/whatif_scenario_comparison.png}
\caption{\textbf{Scenario comparison}---predicted clinical risk probabilities
  under baseline, optimistic, and pessimistic input scenarios.}
\label{fig:scenarios}
\end{figure}
"""

fig_historical = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/whatif_historical_overlay.png}
\caption{\textbf{Historical overlay}---what-if predicted health scores
  superimposed on the actual 10-year wellness trajectory.}
\label{fig:historical}
\end{figure}
"""

# ── 3. Insert figures at appropriate locations ──
# Strategy: insert after specific anchor text patterns

def insert_after(text, anchor, insertion):
    """Insert text after the first occurrence of anchor."""
    pos = text.find(anchor)
    if pos == -1:
        print(f"  WARNING: anchor not found: {anchor[:60]}...")
        return text
    end = pos + len(anchor)
    return text[:end] + "\n" + insertion + text[end:]

# 3a. fig:independence — after H1 rejection paragraph
anchor = r"At least four independent health dimensions exist.\ ($p<0.001$)"
tex = insert_after(tex, anchor, fig_independence)
print("Inserted fig:independence after Section 3.1")

# 3b. fig:aggregation — after H3 rejection paragraph
anchor = r"\textbf{H3 (Equal variance): REJECTED}---Product variance (304.6) exceeds" + "\n" + r"additive variance (89.0).\ ($p<10^{-37}$)"
tex = insert_after(tex, anchor, fig_aggregation)
print("Inserted fig:aggregation after Section 3.2")

# 3c. fig:predictive — after "All 5/5 hypothesis tests"
anchor = r"\textbf{All 5/5 hypothesis tests supported the HEBCS framework.}"
tex = insert_after(tex, anchor, fig_predictive)
print("Inserted fig:predictive after Section 3.5")

# 3d. fig:wellness — after "the primary wellness metric." in Section 3.6
anchor = "the primary wellness metric."
tex = insert_after(tex, anchor, fig_wellness)
print("Inserted fig:wellness in Section 3.6")

# 3e. fig:pathways — after "(Figure~\ref{fig:pathways})."
anchor = r"(Figure~\ref{fig:pathways})."
tex = insert_after(tex, anchor, fig_pathways)
print("Inserted fig:pathways in Section 3.6")

# 3f. fig:shap (NEW) — after "(Figure~\ref{fig:shap})."
anchor = r"(Figure~\ref{fig:shap})."
tex = insert_after(tex, anchor, fig_shap)
print("Inserted fig:shap (NEW) in Section 3.7")

# 3g. What-if figures — after the Fouque2007/Agarwal2010 citation paragraph
anchor = r"blood pressure management in ESRD~\citep{Fouque2007,Agarwal2010}."
whatif_figs = fig_sensitivity + fig_sensitivity_enhanced + fig_heatmap + fig_trajectory + fig_scenarios + fig_historical
tex = insert_after(tex, anchor, whatif_figs)
print("Inserted 6 what-if figures in Section 3.9")

# ── 4. Also update the milestones figure from [htbp] to [htbp] (already correct) ──
# Just in case, ensure it's htbp
# The milestones figure is already inline - no change needed

# ── 5. Write the result ──
tex_path.write_text(tex)
print(f"\n✅ Wrote {len(tex)} chars to {tex_path}")

# Verify all figure labels exist
labels = re.findall(r'\\label\{(fig:\w+)\}', tex)
refs = re.findall(r'\\ref\{(fig:\w+)\}', tex)
print(f"\nFigure labels defined: {labels}")
print(f"Figure refs used: {refs}")
missing = set(refs) - set(labels)
if missing:
    print(f"⚠️  MISSING labels: {missing}")
else:
    print("✅ All figure references resolved")
