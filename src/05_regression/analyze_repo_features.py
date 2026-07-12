import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.db_config import get_mongo_uri
from common.paths import get_output_dir

import argparse as _argparse
_p = _argparse.ArgumentParser(add_help=False)
_args, _ = _p.parse_known_args()
DB_NAME = "upstreamPackagesV2"
MONGO_URI = get_mongo_uri()

import numpy as np
import pandas as pd
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
import statsmodels.api as sm
from scipy import stats
from pymongo import MongoClient

OUT_DIR = Path(get_output_dir())
df = pd.read_csv(OUT_DIR / "repo_features.csv")
print(f"Geladen: {len(df):,}")

# ── Dedup: Repo-Umbenennungen entfernen ──────────────────────────────────────
n0 = len(df)
dh = df[df["stars"] > 10].copy()
dl = df[df["stars"] <= 10].copy()
dh["_o"] = dh["ki_type"].map({"native": 0, "boosted": 1, "non_ai": 2})
dh = dh.sort_values("_o").drop_duplicates(
    subset=["stars", "commits_median", "age_months"], keep="first"
).drop(columns=["_o"])
df = pd.concat([dh, dl], ignore_index=True)
print(f"Dedup: {n0:,} -> {len(df):,}  entfernt={n0-len(df):,}")
print(f"Native={df.native_i.sum():,}  Boosted={df.boosted_i.sum():,}")

# Cluster-ID aus Repo-Name (owner/repo -> owner)
df["owner"] = df["repo"].str.split("/").str[0].fillna("unknown")

# ── Transformationen ─────────────────────────────────────────────────────────
df["log_stars"]   = np.log1p(df["stars"])
df["log_age"]     = np.log1p(df["age_months"])
df["log_commits"] = np.log1p(df["commits_median"])
df["log_contrib"] = np.log1p(df["contributors_median"])
df["log_forks"]   = np.log1p(df["forks"])

# ── Deskriptive Statistik ────────────────────────────────────────────────────
print("\n" + "="*70)
print("DESKRIPTIVE STATISTIK nach Dedup")
for ki in ["non_ai", "native", "boosted"]:
    sub = df[df["ki_type"] == ki]
    print(f"\n  [{ki.upper()}]  n={len(sub):,}")
    for col, lbl in [("stars", "Stars"), ("age_months", "Alter"),
                     ("commits_median", "Commits"), ("contributors_median", "Contributors")]:
        s = sub[col].dropna()
        if len(s) == 0:
            continue
        print(f"    {lbl:<18} Med={s.median():>8.1f}  Mean={s.mean():>9.1f}"
              f"  P25={s.quantile(.25):>7.1f}  P75={s.quantile(.75):>8.1f}")

# ── Spearman Korrelationsmatrix ───────────────────────────────────────────────
AV = ["log_stars", "log_forks", "log_commits", "log_contrib",
      "log_age", "native_i", "boosted_i", "org_i", "perm_i", "n_snapshots"]
VL = {
    "log_stars": "log(Stars)", "log_forks": "log(Forks)",
    "log_commits": "log(Commits)", "log_contrib": "log(Contrib)",
    "log_age": "log(Alter)", "native_i": "AI-Born",
    "boosted_i": "AI-Boost", "org_i": "Org",
    "perm_i": "Perm", "n_snapshots": "Snaps"
}
df_an = df[AV].dropna()
corr = df_an.corr(method="spearman")
lb = [VL.get(v, v) for v in corr.columns]

fig, ax = plt.subplots(figsize=(11, 8))
im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r", aspect="auto")
plt.colorbar(im, ax=ax, shrink=0.8)
ax.set_xticks(range(len(lb))); ax.set_yticks(range(len(lb)))
ax.set_xticklabels(lb, rotation=45, ha="right", fontsize=9)
ax.set_yticklabels(lb, fontsize=9)
for i in range(len(lb)):
    for j in range(len(lb)):
        v = corr.values[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7.5,
                color="white" if abs(v) > 0.4 else "black")
ax.set_title(f"Spearman Korrelation (nach Dedup)  n={len(df_an):,}",
             fontsize=12, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT_DIR / "viz_corr_v2_spearman.png", dpi=150, bbox_inches="tight")
plt.close()
print("Gespeichert: viz_corr_v2_spearman.png")

# ── OLS Hilfsfunktion ─────────────────────────────────────────────────────────
REGRESSORS = ["native_i", "boosted_i", "log_age", "org_i", "perm_i", "log_commits", "log_contrib"]
CLAB = {
    "native_i": "AI-Born (Native)", "boosted_i": "AI-Boosted",
    "log_age": "log(Alter)", "org_i": "Organisation",
    "perm_i": "Permissive Lizenz", "log_commits": "log(Commits)",
    "log_contrib": "log(Contributors)"
}

def run_ols(df_in, cov_type, cov_kwds=None):
    rv = ["log_stars"] + REGRESSORS + (["owner"] if cov_kwds else [])
    df_r = df_in[rv].dropna()
    y = df_r["log_stars"]
    X = sm.add_constant(df_r[REGRESSORS])
    if cov_kwds:
        return sm.OLS(y, X).fit(cov_type=cov_type, cov_kwds=cov_kwds), df_r
    else:
        return sm.OLS(y, X).fit(cov_type=cov_type), df_r

def print_interp(model, label):
    print(f"\n=== INTERPRETATION {label} (exp(b) = multiplikativer Effekt) ===")
    for nm, coef, pv in zip(model.params.index, model.params.values, model.pvalues.values):
        if nm == "const":
            continue
        fc = np.exp(coef)
        pct = (fc - 1) * 100
        sig = "***" if pv < 0.001 else "**" if pv < 0.01 else "*" if pv < 0.05 else "n.s."
        print(f"  {nm:<28} coef={coef:+.4f}  exp(b)={fc:.3f}  {pct:+.1f}%  {sig}")

def plot_coef(model, title, outfile):
    coefs = model.params.drop("const")
    cis   = model.conf_int().drop("const")
    pvs   = model.pvalues.drop("const")
    fig, ax = plt.subplots(figsize=(12, 6))
    ypos = range(len(coefs))
    cols = ["#AAAAAA" if p > 0.05 else ("#2ECC71" if c > 0 else "#E74C3C")
            for c, p in zip(coefs.values, pvs.values)]
    ax.barh(ypos, coefs.values, color=cols, alpha=0.85, height=0.5)
    ax.errorbar(coefs.values, ypos,
                xerr=[coefs.values - cis[0].values, cis[1].values - coefs.values],
                fmt="none", color="#333", capsize=5, linewidth=1.5)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_yticks(ypos)
    ax.set_yticklabels([CLAB.get(c, c) for c in coefs.index], fontsize=10)
    ax.set_xlabel("Koeffizient (AV: log(1+Stars))", fontsize=10)
    ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.3)
    for i, (c, p, hi) in enumerate(zip(coefs.values, pvs.values, cis[1].values)):
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."
        fc = np.exp(c); pct = (fc - 1) * 100
        ax.text(hi + 0.03, i, f"{sig} (x{fc:.2f},{pct:+.0f}%)", va="center", fontsize=8)
    plt.tight_layout()
    plt.savefig(OUT_DIR / outfile, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Gespeichert: {outfile}")

# ── OLS Modell 1: HC3 (Hauptspezifikation) ───────────────────────────────────
print("\n" + "="*70)
print("OLS MODELL 1 — HC3 robuste SE (nach Dedup)")
model_hc3, df_reg = run_ols(df, cov_type="HC3")
print(f"n={len(df_reg):,}  Native={df_reg.native_i.sum():,}  Boosted={df_reg.boosted_i.sum():,}")
print(model_hc3.summary())
print_interp(model_hc3, "HC3")
plot_coef(model_hc3,
          "OLS-Koeffizienten: Determinanten GitHub Stars\nHC3 robuste SE | Gruen=pos.sign. | Grau=n.s.",
          "viz_ols_v2_results.png")

# ── OLS Modell 2: Geclusterte SE nach Owner ──────────────────────────────────
print("\n" + "="*70)
print("OLS MODELL 2 — Geclusterte SE nach Owner (DW-Fix)")
rv_cl = ["log_stars"] + REGRESSORS + ["owner"]
df_cl = df[rv_cl].dropna()
y_cl  = df_cl["log_stars"]
X_cl  = sm.add_constant(df_cl[REGRESSORS])
model_cl = sm.OLS(y_cl, X_cl).fit(
    cov_type="cluster",
    cov_kwds={"groups": df_cl["owner"]}
)
n_clusters = df_cl["owner"].nunique()
print(f"n={len(df_cl):,}  Cluster (Owner)={n_clusters:,}")
print(model_cl.summary())
print_interp(model_cl, "Clustered SE")
plot_coef(model_cl,
          f"OLS-Koeffizienten: Determinanten GitHub Stars\nGeclusterte SE nach Owner ({n_clusters:,} Cluster) | Gruen=pos.sign. | Grau=n.s.",
          "viz_ols_v2_clustered.png")

# ── Vergleich HC3 vs. Clustered ──────────────────────────────────────────────
print("\n=== VERGLEICH HC3 vs. CLUSTERED SE ===")
print(f"  {'Variable':<28}  {'HC3 coef':>10}  {'HC3 p':>8}  {'CL coef':>10}  {'CL p':>8}  {'SE-Aenderung':>14}")
for nm in REGRESSORS:
    b_hc = model_hc3.params[nm];  p_hc = model_hc3.pvalues[nm]
    b_cl = model_cl.params[nm];   p_cl = model_cl.pvalues[nm]
    se_hc = model_hc3.bse[nm];    se_cl = model_cl.bse[nm]
    ratio = se_cl / se_hc if se_hc > 0 else float("nan")
    sig_hc = "***" if p_hc < 0.001 else "**" if p_hc < 0.01 else "*" if p_hc < 0.05 else "n.s."
    sig_cl = "***" if p_cl < 0.001 else "**" if p_cl < 0.01 else "*" if p_cl < 0.05 else "n.s."
    print(f"  {nm:<28}  {b_hc:>+10.4f}  {sig_hc:>8}  {b_cl:>+10.4f}  {sig_cl:>8}  SE x{ratio:.2f}")

# ── Residuen-Diagnostik ───────────────────────────────────────────────────────
resid = model_hc3.resid
print(f"\nResiduen (HC3): Skew={resid.skew():.3f}  Kurt={resid.kurtosis():.3f}")
_, p_sw = stats.shapiro(resid.sample(5000, random_state=42))
print(f"Shapiro p={p_sw:.4f}  (bei grossem n immer sign. — geclusterte SE valide)")

# ── Robustheit: nur stars > 0 ────────────────────────────────────────────────
df_pos = df_reg[df_reg["log_stars"] > 0]
Xp = sm.add_constant(df_pos[REGRESSORS])
mp = sm.OLS(df_pos["log_stars"], Xp).fit(cov_type="HC3")
print(f"\nRobustheit stars>0 (n={len(df_pos):,}) vs alle (n={len(df_reg):,}):")
print(f"  {'Variable':<28}  {'alle':>10}  {'stars>0':>10}  {'diff':>8}")
for nm in ["native_i", "boosted_i", "log_age", "perm_i"]:
    b1 = model_hc3.params[nm]; b2 = mp.params[nm]
    print(f"  {nm:<28}  {b1:>+10.4f}  {b2:>+10.4f}  {b2-b1:>+8.4f}")

# ── Ergebnisse speichern ─────────────────────────────────────────────────────
with open(OUT_DIR / "ols_results.txt", "w") as fout:
    fout.write("=== MODELL 1: HC3 ROBUSTE SE ===\n")
    fout.write(str(model_hc3.summary()))
    fout.write("\n\n=== INTERPRETATION HC3 ===\n")
    for nm, coef, pv in zip(model_hc3.params.index, model_hc3.params.values, model_hc3.pvalues.values):
        if nm == "const": continue
        fc = np.exp(coef); pct = (fc - 1) * 100
        sig = "***" if pv < 0.001 else "**" if pv < 0.01 else "*" if pv < 0.05 else "n.s."
        fout.write(f"  {nm:<28} coef={coef:+.4f}  exp(b)={fc:.3f}  {pct:+.1f}%  {sig}\n")
    fout.write(f"\n\n=== MODELL 2: GECLUSTERTE SE (Owner, {n_clusters:,} Cluster) ===\n")
    fout.write(str(model_cl.summary()))
    fout.write("\n\n=== INTERPRETATION CLUSTERED ===\n")
    for nm, coef, pv in zip(model_cl.params.index, model_cl.params.values, model_cl.pvalues.values):
        if nm == "const": continue
        fc = np.exp(coef); pct = (fc - 1) * 100
        sig = "***" if pv < 0.001 else "**" if pv < 0.01 else "*" if pv < 0.05 else "n.s."
        fout.write(f"  {nm:<28} coef={coef:+.4f}  exp(b)={fc:.3f}  {pct:+.1f}%  {sig}\n")
print("Gespeichert: ols_results_v2.txt")

# ── Stars-Vergleich (viz_29): CSV + MongoDB ───────────────────────────────────
print("\n" + "="*70)
print("STARS-VERGLEICH (viz_29) — aus CSV nach Dedup")

# Primär: aus dem bereits deduplizierten CSV
groups_csv = {
    "non_ai":     df[df["ki_type"] == "non_ai"]["stars"].dropna().tolist(),
    "ai_native":  df[df["ki_type"] == "native"]["stars"].dropna().tolist(),
    "ai_boosted": df[df["ki_type"] == "boosted"]["stars"].dropna().tolist(),
}
print(f"  Non-AI: {len(groups_csv['non_ai']):,}  Native: {len(groups_csv['ai_native']):,}  Boosted: {len(groups_csv['ai_boosted']):,}")

# Zusätzlich: frische Stars aus MongoDB (aktuellerer Stand)
# Hinweis: repoData.stars fehlt in V2 — Fallback auf CSV ist das Normale bei V2
try:
    ki_mapping_path = OUT_DIR / "ki_repo_mapping.json"
    with open(ki_mapping_path, encoding="utf-8") as f:
        ki_data = json.load(f)
    ki_mapping  = ki_data.get("repo_mapping", {})
    native_set  = {r for r, v in ki_mapping.items() if v["ki_type"] == "native"}
    boosted_set = {r for r, v in ki_mapping.items() if v["ki_type"] == "boosted"}

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db_mg  = client[DB_NAME]
    db_mg.command("ping")
    print("  MongoDB verbunden — lade aktuelle Stars...")
    groups_db = {"non_ai": [], "ai_native": [], "ai_boosted": []}
    cursor = db_mg["depsProjects"].find({}, {"_id": 1, "repoData.stars": 1, "stars": 1})
    for doc in cursor:
        repo  = doc["_id"].get("name", "")
        stars = (doc.get("repoData") or {}).get("stars")
        if stars is None:
            stars = doc.get("stars")
        if stars is None or stars < 0:
            continue
        if repo in native_set:
            groups_db["ai_native"].append(stars)
        elif repo in boosted_set:
            groups_db["ai_boosted"].append(stars)
        else:
            groups_db["non_ai"].append(stars)
    cursor.close()
    client.close()
    if not any(groups_db.values()):
        raise ValueError("repoData.stars leer — V2-Datenbank hat dieses Feld nicht")
    groups = groups_db
    source_label = "MongoDB (aktuell)"
    print(f"  Non-AI: {len(groups['non_ai']):,}  Native: {len(groups['ai_native']):,}  Boosted: {len(groups['ai_boosted']):,}")
except Exception as e:
    print(f"  MongoDB-Stars nicht verfuegbar ({e}) — nutze CSV-Daten")
    groups = groups_csv
    source_label = "CSV (nach Dedup)"

labels  = ["Non-AI", "AI-Born\n(Native)", "AI-Boosted"]
keys    = ["non_ai", "ai_native", "ai_boosted"]
colors  = ["#4C72B0", "#55A868", "#C44E52"]
medians = [np.median(groups[k]) if groups[k] else 0 for k in keys]
means   = [np.mean(groups[k])   if groups[k] else 0 for k in keys]
ns      = [len(groups[k]) for k in keys]

fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(labels, medians, color=colors, alpha=0.85, width=0.5, zorder=2)
for i, (med, mn) in enumerate(zip(medians, means)):
    ax.plot(i, mn, marker="D", color="black", markersize=7, zorder=3,
            label="Ø (Durchschnitt)" if i == 0 else "")
    ax.annotate(f"Ø {mn:,.0f}", xy=(i, mn), xytext=(10, 4),
                textcoords="offset points", fontsize=8, color="black")
for bar, med in zip(bars, medians):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
            f"Median: {med:,.0f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
ylim = ax.get_ylim()[1]
for i, n in enumerate(ns):
    ax.text(i, -ylim * 0.06, f"n = {n:,}", ha="center", fontsize=8, color="gray")
ax.set_ylabel("GitHub Stars", fontsize=10)
ax.set_title(f"Stars-Vergleich: Non-AI vs. AI-Born vs. AI-Boosted\n"
             f"(Median-Balken + Ø als Raute | Quelle: {source_label})",
             fontsize=12, fontweight="bold", pad=10)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", alpha=0.3, zorder=0)
ax.legend(loc="upper right", framealpha=0.8)
ax.set_ylim(bottom=0)
plt.tight_layout()
plt.savefig(OUT_DIR / "viz_29_stars_v2.png", dpi=150, bbox_inches="tight")
plt.close()
print("Gespeichert: viz_29_stars_v2.png")

print("\nFertig — analyze_repo_features_v2.py")
