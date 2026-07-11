"""
analyze_repo_features.py

Liest repo_features.csv und erstellt:
  1. Deskriptive Statistik (Tabelle im Terminal)
  2. Korrelationsmatrix als Heatmap (Pearson + Spearman)
  3. OLS-Regression: log_stars ~ native_i + boosted_i + age_months + org_i + perm_i

Output:
  viz_corr_pearson.png
  viz_corr_spearman.png
  viz_ols_results.png
  ols_results.txt
"""

import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.paths import get_output_dir

try:
    import statsmodels.api as sm
    HAS_SM = True
except ImportError:
    HAS_SM = False
    print("WARNUNG: statsmodels nicht installiert. OLS wird uebersprungen.")
    print("  -> pip3 install statsmodels")

OUT_DIR = get_output_dir()
CSV     = OUT_DIR / "repo_features.csv"

print("Lade CSV...")
df = pd.read_csv(CSV)
print(f"  {len(df):,} Zeilen geladen")

# ── Vorbereitung ───────────────────────────────────────────────────────────────

# log-Transformationen fuer schiefe Variablen
df["log_commits_median"]      = np.log1p(df["commits_median"])
df["log_contributors_median"] = np.log1p(df["contributors_median"])
df["log_commits_total"]       = np.log1p(df["commits_total"])
df["log_forks"]               = np.log1p(df["forks"])
df["log_age"]                 = np.log1p(df["age_months"])

# Analyse-Variablen (nur numerisch)
ANALYSIS_VARS = [
    "log_stars",
    "log_forks",
    "log_commits_median",
    "log_contributors_median",
    "log_commits_total",
    "log_age",
    "native_i",
    "boosted_i",
    "org_i",
    "perm_i",
    "n_snapshots",
]

VAR_LABELS = {
    "log_stars":               "log(1+Stars)",
    "log_forks":               "log(1+Forks)",
    "log_commits_median":      "log(1+Commits Median)",
    "log_contributors_median": "log(1+Contributors Median)",
    "log_commits_total":       "log(1+Commits Total)",
    "log_age":                 "log(1+Alter Monate)",
    "native_i":                "AI-Born (0/1)",
    "boosted_i":               "AI-Boosted (0/1)",
    "org_i":                   "Organisation (0/1)",
    "perm_i":                  "Permissive Lizenz (0/1)",
    "n_snapshots":             "Anzahl Panel-Snapshots",
}

df_an = df[ANALYSIS_VARS].dropna()
print(f"  Nach dropna: {len(df_an):,} Zeilen fuer Korrelationsanalyse")

# ── 1. Deskriptive Statistik ────────────────────────────────────────────────────

print("\n=== DESKRIPTIVE STATISTIK ===")
for ki in ["non_ai", "native", "boosted"]:
    sub = df[df["ki_type"] == ki]
    print(f"\n  [{ki.upper()}] n={len(sub):,}")
    for var, raw in [("stars", "stars"), ("age_months", "age_months"),
                     ("commits_median", "commits_median"),
                     ("contributors_median", "contributors_median")]:
        s = sub[raw].dropna()
        if len(s) == 0:
            continue
        print(f"    {var:<25} Median={s.median():>10.1f}  Mean={s.mean():>10.1f}  "
              f"P25={s.quantile(0.25):>8.1f}  P75={s.quantile(0.75):>8.1f}  n={len(s):,}")

# ── 2. Korrelationsmatrix ──────────────────────────────────────────────────────

def plot_corr(corr_matrix, method, filename):
    labels = [VAR_LABELS.get(v, v) for v in corr_matrix.columns]
    fig, ax = plt.subplots(figsize=(13, 10))
    im = ax.imshow(corr_matrix.values, vmin=-1, vmax=1, cmap="RdBu_r", aspect="auto")
    plt.colorbar(im, ax=ax, shrink=0.8, label="Korrelationskoeffizient")

    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(labels, fontsize=9)

    # Werte in Zellen
    for i in range(len(labels)):
        for j in range(len(labels)):
            val = corr_matrix.values[i, j]
            color = "white" if abs(val) > 0.5 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=7.5, color=color, fontweight="bold" if abs(val) > 0.3 else "normal")

    ax.set_title(f"Korrelationsmatrix ({method}) — alle Repo-Variablen\nn={len(df_an):,} Repos",
                 fontsize=13, fontweight="bold", pad=14)
    plt.tight_layout()
    out = OUT_DIR / filename
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Gespeichert: {out.name}")

print("\nBerechne Pearson-Korrelation...")
corr_pearson  = df_an.corr(method="pearson")
plot_corr(corr_pearson,  "Pearson",  "viz_corr_pearson.png")

print("Berechne Spearman-Korrelation...")
corr_spearman = df_an.corr(method="spearman")
plot_corr(corr_spearman, "Spearman", "viz_corr_spearman.png")

# ── 3. OLS-Regression ───────────────────────────────────────────────────────────

if HAS_SM:
    print("\nOLS-Regression...")

    reg_vars = ["log_stars", "native_i", "boosted_i", "log_age", "org_i", "perm_i",
                "log_commits_median", "log_contributors_median"]
    df_reg = df[reg_vars].dropna()
    print(f"  Stichprobe: {len(df_reg):,} Repos")

    y = df_reg["log_stars"]
    X = df_reg[["native_i", "boosted_i", "log_age", "org_i", "perm_i",
                "log_commits_median", "log_contributors_median"]]
    X = sm.add_constant(X)

    model  = sm.OLS(y, X).fit(cov_type="HC3")  # robuste SE
    summary = model.summary()
    print(summary)

    # Speichern als Text
    with open(OUT_DIR / "ols_results.txt", "w") as f:
        f.write(str(summary))
    print("  Gespeichert: ols_results.txt")

    # Koeffizienten-Plot
    coefs  = model.params.drop("const")
    cis    = model.conf_int().drop("const")
    pvals  = model.pvalues.drop("const")

    COEF_LABELS = {
        "native_i":                "AI-Born (Native)",
        "boosted_i":               "AI-Boosted",
        "log_age":                 "log(Alter)",
        "org_i":                   "Organisation",
        "perm_i":                  "Permissive Lizenz",
        "log_commits_median":      "log(Commits Median)",
        "log_contributors_median": "log(Contributors Median)",
    }

    labels_plot = [COEF_LABELS.get(c, c) for c in coefs.index]
    colors_plot = []
    for c, p in zip(coefs.values, pvals.values):
        if p > 0.05:
            colors_plot.append("#AAAAAA")
        elif c > 0:
            colors_plot.append("#2ECC71")
        else:
            colors_plot.append("#E74C3C")

    fig, ax = plt.subplots(figsize=(9, 6))
    y_pos = range(len(coefs))
    ax.barh(y_pos, coefs.values, color=colors_plot, alpha=0.85, height=0.5)
    ax.errorbar(coefs.values, y_pos,
                xerr=[coefs.values - cis[0].values, cis[1].values - coefs.values],
                fmt="none", color="black", capsize=5, linewidth=1.5)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels_plot, fontsize=10)
    ax.set_xlabel("Koeffizient (log_stars)", fontsize=10)
    ax.set_title("OLS-Koeffizienten: Determinanten von GitHub Stars\n"
                 "(HC3 robuste SE | Grün = positiv signif. | Rot = negativ signif. | Grau = n.s.)",
                 fontsize=11, fontweight="bold", pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.3)

    # Signifikanz-Sterne
    for i, (coef, p) in enumerate(zip(coefs.values, pvals.values)):
        stars_sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."
        ax.text(cis[1].values[i] + 0.02, i, stars_sig, va="center", fontsize=9)

    plt.tight_layout()
    out = OUT_DIR / "viz_ols_results.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Gespeichert: {out.name}")

print("\nFertig.")
