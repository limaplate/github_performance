"""
regression.py
================================================================================
Vollständige OLS-Regressionsanalyse: Determinanten von GitHub-Popularität (Stars)
im PyPI-Open-Source-Ökosystem mit Fokus auf KI-Klassifikation.

Forschungsfrage:
  Sind KI-Repositories signifikant populärer als vergleichbare Non-AI-Repositories,
  unter Kontrolle relevanter Projektmerkmale?

  Erweiterung (Prof-Feedback): Moderiert die Stärke des KI-Effekts durch
  Community-Größe, Projektalter oder Lizenztyp?

================================================================================
DATENQUELLEN
================================================================================

Alle Variablen stammen aus repo_features.csv, die durch build_repo_features.py
aus der MongoDB-Datenbank (upstreamPackages) gezogen wurde.

  Collection depsProjects:
    → stars          (repoData.stars)      — Snapshot-Gesamtzahl der GitHub-Stars
    → forks          (repoData.forks)      — Gesamtzahl der GitHub-Forks
    → created_at     (repoData.created_at) — Gründungsdatum → age_months
    → org_i          (ownerData.type)      — 1 wenn Organisation, 0 wenn Privatperson
    → perm_i         (repoData.license)    — 1 wenn permissive Lizenz (MIT/Apache/BSD/...)
    → license_cat                          — Permissiv / Copyleft / Andere (dreistufig)

  Collection depsProjectsPanel (monatliche Snapshots je Repo):
    → commits_median     — Median der monatl. Commits über alle Snapshots
    → contributors_median— Median der monatl. Contributors über alle Snapshots
    → commits_total      — Summe aller Commits
    → n_snapshots        — Anzahl Panel-Einträge (≈ aktive Beobachtungsmonate)

  KI-Klassifikation (ki_repo_mapping.json, via build_ki_repo_mapping.py):
    → ki_type            — 'native' / 'boosted' / 'non_ai'
    → native_i           — 1 wenn AI-Born (KI-Dependency bereits beim ersten Release)
    → boosted_i          — 1 wenn AI-Boosted (KI-Dependency nachträglich hinzugefügt)
    Referenzkategorie (implizit): non_ai (= kein KI-Signal in Signal A oder B)

================================================================================
VARIABLEN-TRANSFORMATION
================================================================================

  AV:  log_stars     = log(1 + stars)
       Begründung: stars ist extrem rechtschief (Median ~2, Max ~100k+).
       log1p komprimiert die Skala und verarbeitet Null-Werte.
       Koeffizient-Interpretation: exp(β) - 1 = prozentualer Effekt auf rohe Stars.

  UV:  log_age       = log(1 + age_months)
       log_contrib   = log(1 + contributors_median)
       log_commits   = log(1 + commits_median)
       Begründung: alle drei sind rechtschief. log1p-Transformation erzeugt
       annähernd normalverteilte Prädiktoren und erlaubt Elastizitäts-Interpretation.

       native_i, boosted_i, org_i, perm_i — binäre Dummies, keine Transformation.

  Zentrierung für Interaktionsterme:
       log_contrib_c  = log_contrib  - mean(log_contrib)
       log_age_c      = log_age      - mean(log_age)
       Begründung: Mean-Centering verhindert Multikollinearität zwischen
       Haupteffekt und Interaktionsterm. Die Interpretation des Haupteffekts
       (ai_i) nach Zentrierung: Effekt für ein Repo mit durchschnittlichem
       Contributors-/Alters-Wert (= sinnvollster Referenzpunkt).

================================================================================
MODELL-ARCHITEKTUR
================================================================================

  M1  — Hauptmodell: native_i + boosted_i + alle Controls, HC3 robuste SE
         Replikation und Erweiterung des bestehenden Modells (analog analyze_v2.py).
         Zweck: Kernantwort auf Forschungsfrage. Identifiziert ob und wie stark
         KI-Status mit Popularität assoziiert ist.

  M2  — Robustheit: identisch M1, aber geclusterte SE nach Owner (115k+ Cluster)
         Begründung: Ein Entwickler/eine Org hat oft mehrere Repos. Diese sind
         nicht unabhängig (populärer Owner → Sichtbarkeitsbonus für alle Repos).
         Geclusterte SE korrigiert die Unterschätzung der wahren Unsicherheit.
         Koeffizienten identisch mit M1, nur SE und p-Werte konservativer.

  M3a — Wald-Test + kombinierter AI-Dummy: ai_i = max(native_i, boosted_i)
         Voraussetzung: Wald-Test H0: β(native_i) = β(boosted_i).
         Wenn H0 nicht abgelehnt → kombinierter Dummy berechtigt und einfacher
         für Moderationsanalyse. M3a ist Basis-Modell für M3b-M3d.

  M3b — Moderator Contributors: M3a + ai_i × log_contrib_c
         Hypothese: Der KI-Popularitäts-Bonus verstärkt sich mit wachsender
         Community (Netzwerkeffekt-Logik). KI-Projekte mit mehr Contributors
         profitieren überproportional von Sichtbarkeits-Spill-overs.
         Erwartetes Vorzeichen: positiv (+).

  M3c — Moderator Alter: M3a + ai_i × log_age_c
         Hypothese: Jüngere KI-Projekte profitieren stärker vom Post-2022-
         Hype-Effekt (ChatGPT-Kulmination). Ältere KI-Projekte (pre-2022)
         wurden weniger durch den Trend begünstigt.
         Erwartetes Vorzeichen: negativ (–), da jüngere Repos mit KI mehr Bonus.

  M3d — Moderator Lizenz: M3a + ai_i × perm_i
         Hypothese: KI-Projekte mit permissiver Lizenz sind doppelt bevorzugt:
         KI-Hype + keine Adoptionsbarriere für Unternehmen. Synergieeffekt.
         Erwartetes Vorzeichen: positiv (+).

  M4  — Robustheit Multikollinearität: M1 ohne log_commits (nur log_contrib)
         Begründung: commits und contributors sind hoch korreliert (beide aus
         Panel-Aktivität). M4 prüft ob Koeffizienten stabil bleiben wenn nur
         der theoretisch besser begründete Indikator (Community-Breite vs.
         Entwicklungsintensität) verwendet wird.

  M5  — Alternative AV: log_forks statt log_stars
         Begründung: Forks messen aktive Nutzungsintention (jemand kopiert das
         Repo um daran weiterzuarbeiten) — weniger passiv als Stars (Bookmarking).
         Wenn β(ai_i) mit Forks ähnlich stark wie mit Stars → robuster Befund.

================================================================================
HYPOTHESEN
================================================================================

  H1: AI-Born-Repos haben signifikant mehr Stars als Non-AI-Repos (ceteris paribus).
  H2: AI-Boosted-Repos haben signifikant mehr Stars als Non-AI-Repos (ceteris paribus).
  H3: Der Unterschied zwischen AI-Born und AI-Boosted ist nicht signifikant
      (Wald-Test) → kombinierter Dummy ai_i berechtigt.
  H4: Der KI-Popularitäts-Bonus ist für Repos mit mehr Contributors stärker
      (Interaktionsterm ai_i × log_contrib_c positiv und signifikant).
  H5: Der KI-Popularitäts-Bonus ist für jüngere Repos stärker
      (Interaktionsterm ai_i × log_age_c negativ und signifikant).
  H6: Der KI-Popularitäts-Bonus ist für permissiv lizenzierte Repos stärker
      (Interaktionsterm ai_i × perm_i positiv und signifikant).

================================================================================
OUTPUT-DATEIEN
================================================================================

  regression_results.txt          — Vollständige Modell-Outputs (print-Protokoll)
  regression_table.csv            — Paper-ready Koeffiziententabelle alle Modelle
  viz_reg_m1_coefs.png            — Koeffizientenplot M1 (Hauptmodell)
  viz_reg_m3_moderators.png       — Koeffizientenplot M3b/c/d (Moderatoren)
  viz_reg_interactions.png        — Interaktionsplots (Marginal Effects)
  viz_reg_vif.png                 — VIF-Übersicht aller Modelle

================================================================================
AUTOR & DATUM
================================================================================
  Bachelorarbeit — Python Open-Source KI-Analyse
  Stand: Juni 2026
"""

# ==============================================================================
# IMPORTS
# ==============================================================================
import numpy as np
import pandas as pd
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from scipy import stats
import warnings
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.paths import get_output_dir
warnings.filterwarnings("ignore", category=FutureWarning)

# ==============================================================================
# KONFIGURATION
# ==============================================================================
OUT_DIR = get_output_dir()
CSV_PATH = OUT_DIR / "repo_features.csv"
LOG_PATH = OUT_DIR / "regression_results.txt"
TAB_PATH = OUT_DIR / "regression_table.csv"

# Signifikanzlevel
ALPHA = 0.05

# Logging: alles in Datei UND auf Konsole
log_lines = []

def log(msg=""):
    """Schreibt nach stdout und in log_lines-Puffer."""
    print(msg)
    log_lines.append(str(msg))

def save_log():
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))
    print(f"\n→ Log gespeichert: {LOG_PATH}")

def ts():
    return datetime.now().strftime("%H:%M:%S")

# ==============================================================================
# DATEN LADEN
# ==============================================================================
log(f"[{ts()}] Lade repo_features.csv ...")
df = pd.read_csv(CSV_PATH)
log(f"  Geladen: {len(df):,} Zeilen")
log(f"  Spalten: {list(df.columns)}")

# ==============================================================================
# DEDUPLICATION
# Repositories können bei GitHub-Umbenennung unter altem + neuem Namen in der
# Panel-Collection auftauchen. Fingerprint (stars, commits_median, age_months)
# identifiziert Duplikate. Priorisierung: native > boosted > non_ai.
# ==============================================================================
n0 = len(df)
dh = df[df["stars"] > 10].copy()
dl = df[df["stars"] <= 10].copy()
dh["_o"] = dh["ki_type"].map({"native": 0, "boosted": 1, "non_ai": 2})
dh = dh.sort_values("_o").drop_duplicates(
    subset=["stars", "commits_median", "age_months"], keep="first"
).drop(columns=["_o"])
df = pd.concat([dh, dl], ignore_index=True)
log(f"  Dedup: {n0:,} → {len(df):,}  (entfernt: {n0-len(df):,})")
log(f"  Native={df.native_i.sum():,}  Boosted={df.boosted_i.sum():,}  "
    f"Non-AI={((df.native_i==0)&(df.boosted_i==0)).sum():,}")

# Cluster-ID: Owner aus 'owner/repo'
df["owner"] = df["repo"].str.split("/").str[0].fillna("unknown")

# ==============================================================================
# VARIABLEN-TRANSFORMATION
# ==============================================================================
log(f"\n[{ts()}] Variablen transformieren ...")

# Abhängige Variable
df["log_stars"]   = np.log1p(df["stars"])
df["log_forks"]   = np.log1p(df["forks"])          # Alternative AV (M5)

# Kontinuierliche Prädiktoren → log1p (rechtsschiefe Verteilungen)
df["log_age"]     = np.log1p(df["age_months"])
df["log_contrib"] = np.log1p(df["contributors_median"])
df["log_commits"] = np.log1p(df["commits_median"])

# Kombinierter AI-Dummy (für M3a–M3d, M5)
df["ai_i"] = ((df["native_i"] == 1) | (df["boosted_i"] == 1)).astype(int)

# Copyleft-Dummy (für erweiterte Lizenz-Analyse)
df["copyleft_i"] = (df["license_cat"] == "Copyleft").astype(int)

# Mean-Centering für Interaktionsterme (verhindert Multikollinearität)
# Referenz: Aiken & West (1991) — standard bei Moderationsanalyse
df["log_contrib_c"] = df["log_contrib"] - df["log_contrib"].mean()
df["log_age_c"]     = df["log_age"]     - df["log_age"].mean()

# Interaktionsterme
df["ai_x_contrib"] = df["ai_i"] * df["log_contrib_c"]
df["ai_x_age"]     = df["ai_i"] * df["log_age_c"]
df["ai_x_perm"]    = df["ai_i"] * df["perm_i"]

# Deskriptive Statistik der transformierten Variablen
log("\n--- Deskriptive Statistik transformierter Variablen ---")
transf_vars = ["log_stars", "log_age", "log_contrib", "log_commits",
               "native_i", "boosted_i", "ai_i", "org_i", "perm_i"]
log(df[transf_vars].describe().round(3).to_string())

# Stichprobengrößen
log(f"\nMean log_contrib (vor Centering): {df['log_contrib'].mean():.4f}")
log(f"Mean log_age     (vor Centering): {df['log_age'].mean():.4f}")
log(f"Mean log_contrib_c (nach):        {df['log_contrib_c'].mean():.6f}  (≈ 0 erwartet)")
log(f"Mean log_age_c     (nach):        {df['log_age_c'].mean():.6f}  (≈ 0 erwartet)")

# ==============================================================================
# HILFSFUNKTIONEN
# ==============================================================================

# Labels für Visualisierungen
CLAB = {
    "native_i":       "AI-Born (Native)",
    "boosted_i":      "AI-Boosted",
    "ai_i":           "KI-Projekt (ai_i)",
    "log_age":        "log(Alter)",
    "log_age_c":      "log(Alter) zentriert",
    "org_i":          "Organisation",
    "perm_i":         "Permissive Lizenz",
    "copyleft_i":     "Copyleft Lizenz",
    "log_commits":    "log(Commits/Monat)",
    "log_contrib":    "log(Contributors/Monat)",
    "log_contrib_c":  "log(Contributors) zentriert",
    "ai_x_contrib":   "KI × log(Contributors)",
    "ai_x_age":       "KI × log(Alter)",
    "ai_x_perm":      "KI × Permissive Lizenz",
}


def sig_stars(p):
    """Gibt Signifikanzsterne zurück."""
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    return "n.s."


def print_interpretation(model, label):
    """Druckt exp(β) und prozentuale Effektgröße je Variable."""
    log(f"\n=== INTERPRETATION {label} ===")
    log(f"  {'Variable':<28}  {'coef':>8}  {'exp(β)':>8}  {'Effekt%':>9}  {'p':>8}  {'Sig':>5}")
    log(f"  {'-'*75}")
    for nm in model.params.index:
        if nm == "const":
            continue
        coef = model.params[nm]
        pv   = model.pvalues[nm]
        fc   = np.exp(coef)
        pct  = (fc - 1) * 100
        sig  = sig_stars(pv)
        log(f"  {nm:<28}  {coef:>+8.4f}  {fc:>8.3f}  {pct:>+9.1f}%  {pv:>8.4f}  {sig:>5}")
    log(f"  R² = {model.rsquared:.4f}   Adj. R² = {model.rsquared_adj:.4f}   n = {int(model.nobs):,}")


def run_ols(df_in, regressors, label, cov_type="HC3", cluster_var=None):
    """
    Führt OLS mit gewählten Regressoren aus.
    Returns: (fitted_model, df_used)
    """
    needed = ["log_stars"] + regressors + ([cluster_var] if cluster_var else [])
    df_r = df_in[needed].dropna()
    y = df_r["log_stars"]
    X = sm.add_constant(df_r[regressors])
    if cluster_var:
        model = sm.OLS(y, X).fit(
            cov_type="cluster",
            cov_kwds={"groups": df_r[cluster_var]}
        )
    else:
        model = sm.OLS(y, X).fit(cov_type=cov_type)
    log(f"\n{'='*70}")
    log(f"MODELL {label}")
    log(f"  cov_type = {cov_type if not cluster_var else 'cluster (' + cluster_var + ')'}")
    log(f"  n = {len(df_r):,}")
    if "native_i" in df_r.columns:
        log(f"  Native={df_r['native_i'].sum():,}  Boosted={df_r['boosted_i'].sum():,}")
    if "ai_i" in df_r.columns:
        log(f"  ai_i=1: {df_r['ai_i'].sum():,}")
    log(model.summary().as_text())
    print_interpretation(model, label)
    return model, df_r


def plot_coef(model, title, outfile, clab=None):
    """Erstellt horizontalen Koeffizientenplot mit CIs."""
    if clab is None:
        clab = CLAB
    coefs = model.params.drop("const")
    cis   = model.conf_int().drop("const")
    pvs   = model.pvalues.drop("const")

    fig, ax = plt.subplots(figsize=(13, max(5, len(coefs) * 0.65)))
    ypos = range(len(coefs))
    cols = ["#AAAAAA" if p > ALPHA else ("#2ECC71" if c > 0 else "#E74C3C")
            for c, p in zip(coefs.values, pvs.values)]
    ax.barh(ypos, coefs.values, color=cols, alpha=0.80, height=0.5)
    ax.errorbar(
        coefs.values, ypos,
        xerr=[coefs.values - cis[0].values, cis[1].values - coefs.values],
        fmt="none", color="#222", capsize=5, linewidth=1.5
    )
    ax.axvline(0, color="black", linewidth=1.2)
    ax.set_yticks(ypos)
    ax.set_yticklabels([clab.get(c, c) for c in coefs.index], fontsize=10)
    ax.set_xlabel("Koeffizient (AV: log(1+Stars))", fontsize=10)
    ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    for i, (c, p, hi) in enumerate(zip(coefs.values, pvs.values, cis[1].values)):
        sig  = sig_stars(p)
        fc   = np.exp(c)
        pct  = (fc - 1) * 100
        ax.text(hi + 0.03, i,
                f"{sig}  x{fc:.2f} ({pct:+.0f}%)",
                va="center", fontsize=8, color="#333")
    plt.tight_layout()
    plt.savefig(OUT_DIR / outfile, dpi=150, bbox_inches="tight")
    plt.close()
    log(f"  → Plot gespeichert: {outfile}")


def compute_vif(df_in, regressors):
    """Berechnet VIF für eine Liste von Regressoren."""
    df_r = df_in[regressors].dropna()
    X = sm.add_constant(df_r)
    vif_vals = [
        variance_inflation_factor(X.values, i)
        for i in range(X.shape[1])
    ]
    vif_df = pd.DataFrame({"Variable": X.columns, "VIF": vif_vals})
    vif_df = vif_df[vif_df.Variable != "const"].sort_values("VIF", ascending=False)
    return vif_df


def make_results_table(models_dict):
    """
    Erstellt Paper-ready Koeffiziententabelle.
    Format: Zeilen = Variablen, Spalten = Modelle.
    Zellen: coef*** (SE).
    """
    all_vars = []
    for model in models_dict.values():
        for v in model.params.index:
            if v != "const" and v not in all_vars:
                all_vars.append(v)

    records = {}
    for var in all_vars:
        row = {}
        for mname, model in models_dict.items():
            if var in model.params.index:
                b   = model.params[var]
                se  = model.bse[var]
                p   = model.pvalues[var]
                sig = sig_stars(p)
                row[mname]            = f"{b:.3f}{sig}"
                row[mname + "_se"]    = f"({se:.3f})"
            else:
                row[mname]         = "—"
                row[mname + "_se"] = ""
        records[var] = row

    df_tab = pd.DataFrame(records).T

    # Statistiken anhängen
    stats_rows = {}
    for mname, model in models_dict.items():
        stats_rows.setdefault("N", {})[mname] = f"{int(model.nobs):,}"
        stats_rows.setdefault("R²", {})[mname] = f"{model.rsquared:.3f}"
        stats_rows.setdefault("Adj. R²", {})[mname] = f"{model.rsquared_adj:.3f}"
        stats_rows.setdefault("N", {})[mname + "_se"] = ""
        stats_rows.setdefault("R²", {})[mname + "_se"] = ""
        stats_rows.setdefault("Adj. R²", {})[mname + "_se"] = ""

    df_stats = pd.DataFrame(stats_rows).T
    df_tab = pd.concat([df_tab, df_stats])
    df_tab.to_csv(TAB_PATH, encoding="utf-8")
    log(f"  → Regressionstabelle gespeichert: {TAB_PATH}")
    log("\n" + df_tab.to_string())
    return df_tab


# ==============================================================================
# KORRELATIONSCHECK: COMMITS vs. CONTRIBUTORS
# Prüft die Stärke der Multikollinearität vor Modellschätzung.
# ==============================================================================
log(f"\n{'='*70}")
log("PRE-CHECK: Spearman-Korrelation commits vs. contributors")
corr_vars = ["log_stars", "log_contrib", "log_commits", "log_age",
             "native_i", "boosted_i", "ai_i", "org_i", "perm_i"]
df_corr = df[corr_vars].dropna()
corr_matrix = df_corr.corr(method="spearman").round(3)
log(corr_matrix.to_string())
r_cc = corr_matrix.loc["log_commits", "log_contrib"]
log(f"\nSpearman r(log_commits, log_contrib) = {r_cc:.3f}")
if abs(r_cc) > 0.7:
    log("  ⚠️  Hohe Korrelation — Multikollinearität zwischen commits und contrib.")
    log("      M4 (nur contrib) wird als Robustheit benötigt.")
else:
    log("  ✅ Korrelation moderat — beide im Modell vertretbar, M4 als Check.")


# ==============================================================================
# MODELL M1 — HAUPTMODELL (HC3 robuste SE)
# native_i + boosted_i + log_age + org_i + perm_i + log_commits + log_contrib
# Entspricht dem bisherigen Modell in analyze_repo_features_v2.py.
# Zweck: Kernbefund H1 und H2.
# ==============================================================================
REGR_M1 = ["native_i", "boosted_i", "log_age", "org_i",
           "perm_i", "log_commits", "log_contrib"]

m1_hc3, df_m1 = run_ols(df, REGR_M1, "M1 — Hauptmodell (HC3)", cov_type="HC3")

plot_coef(
    m1_hc3,
    "M1 Hauptmodell: Determinanten GitHub Stars\n"
    "HC3 robuste SE | Grün=pos.sig. | Grau=n.s. | n={}\n"
    "Ref.-kategorie: Non-AI-Repos".format(int(m1_hc3.nobs)),
    "viz_reg_m1_coefs.png"
)

# VIF M1
log("\nVIF-Check M1:")
vif_m1 = compute_vif(df, REGR_M1)
log(vif_m1.to_string())
if (vif_m1.VIF > 10).any():
    log("  ⚠️  VIF > 10 — Multikollinearitätsproblem in M1!")
else:
    log("  ✅ Alle VIF < 10 in M1")


# ==============================================================================
# MODELL M2 — ROBUSTHEIT: GECLUSTERTE SE NACH OWNER
# Identische Koeffizienten wie M1, aber SE nach Owner geclustert.
# Begründung: Repos desselben Owners sind nicht unabhängig.
# Ergebnis: konservativere (größere) SE, validiert Signifikanz.
# ==============================================================================
m2_cl, df_m2 = run_ols(
    df, REGR_M1, "M2 — Robustheit geclusterte SE (Owner)",
    cov_type="cluster", cluster_var="owner"
)
n_cluster = df_m2["owner"].nunique()
log(f"  Owner-Cluster: {n_cluster:,}")

# Vergleich HC3 vs. Clustered SE
log("\n--- Vergleich M1 (HC3) vs. M2 (Clustered SE) ---")
log(f"  {'Variable':<28}  {'HC3 coef':>10}  {'HC3 sig':>8}  {'SE-Ratio (CL/HC3)':>18}  {'CL sig':>8}")
for nm in REGR_M1:
    b1  = m1_hc3.params[nm];  p1 = m1_hc3.pvalues[nm]
    se1 = m1_hc3.bse[nm]
    se2 = m2_cl.bse[nm];      p2 = m2_cl.pvalues[nm]
    ratio = se2 / se1 if se1 > 0 else float("nan")
    log(f"  {nm:<28}  {b1:>+10.4f}  {sig_stars(p1):>8}  {ratio:>18.2f}x  {sig_stars(p2):>8}")


# ==============================================================================
# WALD-TEST: β(native_i) = β(boosted_i)
# Prüft H3: Gibt es einen signifikanten Unterschied zwischen AI-Born und
# AI-Boosted in ihrer Assoziation mit Popularität?
# Falls H3 nicht abgelehnt → kombinierter ai_i-Dummy für M3a–M3d berechtigt.
# ==============================================================================
log(f"\n{'='*70}")
log("WALD-TEST: H0: β(native_i) = β(boosted_i)")
wald = m1_hc3.wald_test("native_i = boosted_i")
wald_stat = float(np.asarray(wald.statistic).squeeze())
wald_p = float(np.asarray(wald.pvalue).squeeze())
wald_df = getattr(wald, "df_denom", None)
log(f"  Teststatistik = {wald_stat:.4f}")
if wald_df is not None:
    log(f"  df = {wald_df}")
log(f"  p-Wert       = {wald_p:.4f}")
log(f"  Δβ = {m1_hc3.params['native_i'] - m1_hc3.params['boosted_i']:+.4f}")
if wald_p < ALPHA:
    log(f"  → H3 ABGELEHNT (p={wald_p:.4f}): native ≠ boosted (sign. Unterschied)")
    log("    Getrennte Dummies native_i / boosted_i bleiben in Hauptmodell.")
    log("    M3a mit kombiniertem ai_i ist methodisch eine Vereinfachung, muss begründet werden.")
else:
    log(f"  → H3 NICHT ABGELEHNT (p={wald_p:.4f}): kein sign. Unterschied native vs. boosted")
    log("    Kombinierter ai_i-Dummy für M3a–M3d methodisch berechtigt.")


# ==============================================================================
# MODELL M3a — KOMBINIERTER AI-DUMMY (Basis für Moderationsanalyse)
# ai_i = 1 wenn native ODER boosted; Referenz = Non-AI
# Voraussetzung: Wald-Test nicht signifikant (H3 nicht abgelehnt).
# ==============================================================================
REGR_M3A = ["ai_i", "log_age", "org_i", "perm_i", "log_commits", "log_contrib"]

m3a, df_m3a = run_ols(df, REGR_M3A, "M3a — Kombinierter AI-Dummy (HC3)", cov_type="HC3")

# Vergleich M1 vs. M3a: wie stark ändert sich β(KI) durch Zusammenlegen?
log("\n--- Vergleich M1 (native/boosted getrennt) vs. M3a (kombiniert ai_i) ---")
log(f"  M1 native_i:  {m1_hc3.params['native_i']:+.4f} ({sig_stars(m1_hc3.pvalues['native_i'])})")
log(f"  M1 boosted_i: {m1_hc3.params['boosted_i']:+.4f} ({sig_stars(m1_hc3.pvalues['boosted_i'])})")
log(f"  M3a ai_i:     {m3a.params['ai_i']:+.4f} ({sig_stars(m3a.pvalues['ai_i'])})")
log(f"  R² M1={m1_hc3.rsquared:.4f}  R² M3a={m3a.rsquared:.4f}")


# ==============================================================================
# MODELL M3b — MODERATOR 1: CONTRIBUTORS × KI
# Hypothese H4: Der KI-Popularitätsbonus steigt mit der Community-Größe.
# Mechanismus: Größere Communities generieren mehr organische Sichtbarkeit;
# bei KI-Projekten potenziert Hype diesen Netzwerkeffekt.
# Interaktionsterm: ai_i × log_contrib_c (mean-zentriert)
# Erwartetes Vorzeichen: positiv (+)
# ==============================================================================
REGR_M3B = ["ai_i", "log_contrib_c", "ai_x_contrib",
            "log_age", "org_i", "perm_i", "log_commits"]

m3b, df_m3b = run_ols(df, REGR_M3B, "M3b — Moderator Contributors × KI (HC3)", cov_type="HC3")

# VIF M3b
log("\nVIF-Check M3b:")
vif_m3b = compute_vif(df, REGR_M3B)
log(vif_m3b.to_string())
if (vif_m3b.VIF > 10).any():
    log("  ⚠️  VIF > 10 in M3b — Mean-Centering hat Multikollinearität nicht vollständig eliminiert.")
else:
    log("  ✅ Alle VIF < 10 in M3b — Mean-Centering erfolgreich.")


# ==============================================================================
# MODELL M3c — MODERATOR 2: ALTER × KI
# Hypothese H5: Jüngere KI-Repos profitieren stärker vom Post-2022-Hype.
# Mechanismus: KI-Projekte, die nach dem ChatGPT-Durchbruch gegründet wurden,
# entstanden in einem Ökosystem mit maximalem Sichtbarkeits-Tailwind.
# Interaktionsterm: ai_i × log_age_c (mean-zentriert)
# Erwartetes Vorzeichen: negativ (–), da jüngere Repos → kleineres log_age_c
# und trotzdem hoher KI-Bonus.
# ==============================================================================
REGR_M3C = ["ai_i", "log_age_c", "ai_x_age",
            "org_i", "perm_i", "log_commits", "log_contrib"]

m3c, df_m3c = run_ols(df, REGR_M3C, "M3c — Moderator Alter × KI (HC3)", cov_type="HC3")

log("\nVIF-Check M3c:")
vif_m3c = compute_vif(df, REGR_M3C)
log(vif_m3c.to_string())
if (vif_m3c.VIF > 10).any():
    log("  ⚠️  VIF > 10 in M3c")
else:
    log("  ✅ Alle VIF < 10 in M3c")


# ==============================================================================
# MODELL M3d — MODERATOR 3: LIZENZ × KI
# Hypothese H6: KI + permissive Lizenz erzeugt Synergie-Effekt.
# Mechanismus: Permissive Lizenzen (MIT/Apache) entfernen Adoptionsbarrieren
# für Unternehmen; kombiniert mit KI-Kontext maximiert das die Reichweite.
# Interaktionsterm: ai_i × perm_i (kein Centering nötig, da perm_i binär)
# Erwartetes Vorzeichen: positiv (+)
# ==============================================================================
REGR_M3D = ["ai_i", "perm_i", "ai_x_perm",
            "log_age", "org_i", "log_commits", "log_contrib"]

m3d, df_m3d = run_ols(df, REGR_M3D, "M3d — Moderator Lizenz × KI (HC3)", cov_type="HC3")

log("\nVIF-Check M3d:")
vif_m3d = compute_vif(df, REGR_M3D)
log(vif_m3d.to_string())
if (vif_m3d.VIF > 10).any():
    log("  ⚠️  VIF > 10 in M3d")
else:
    log("  ✅ Alle VIF < 10 in M3d")


# ==============================================================================
# MODELL M4 — ROBUSTHEIT: NUR CONTRIBUTORS (ohne Commits)
# Prüft ob β(native_i) und β(boosted_i) stabil bleiben wenn log_commits
# weggelassen wird. Begründung: Hohe Korrelation zwischen commits und contrib
# → Multikollinearitäts-Robustheit.
# ==============================================================================
REGR_M4 = ["native_i", "boosted_i", "log_age", "org_i", "perm_i", "log_contrib"]

m4, df_m4 = run_ols(df, REGR_M4, "M4 — Robustheit ohne log_commits (HC3)", cov_type="HC3")

# Vergleich M1 vs. M4: Stabilität der Hauptkoeffizienten
log("\n--- Stabilitätsvergleich M1 vs. M4 (ohne commits) ---")
log(f"  {'Variable':<20}  {'M1 coef':>10}  {'M4 coef':>10}  {'Δ':>8}")
for nm in ["native_i", "boosted_i", "log_age", "org_i", "perm_i", "log_contrib"]:
    b1 = m1_hc3.params[nm]
    b4 = m4.params[nm]
    log(f"  {nm:<20}  {b1:>+10.4f}  {b4:>+10.4f}  {b4-b1:>+8.4f}")
if max(abs(m4.params["native_i"] - m1_hc3.params["native_i"]),
       abs(m4.params["boosted_i"] - m1_hc3.params["boosted_i"])) < 0.05:
    log("  ✅ Koeffizienten stabil — Multikollinearität kein ernstes Problem.")
else:
    log("  ⚠️  Koeffizienten ändern sich merklich — commits und contrib redundant.")


# ==============================================================================
# MODELL M5 — ALTERNATIVE AV: log_forks statt log_stars
# Forks messen aktive Nutzungsintention (Kopie zum Weiterentwickeln) vs.
# Stars (passives Bookmarking). Wenn β(native_i) ähnlich stark → robuster Befund.
# ==============================================================================
log(f"\n{'='*70}")
log("MODELL M5 — Alternative AV: log_forks")

# Prüfen ob forks vorhanden und ausreichend befüllt
n_forks_valid = df["log_forks"].notna().sum()
log(f"  log_forks vorhanden: {n_forks_valid:,} / {len(df):,} Repos")

if n_forks_valid > 10000:
    REGR_M5 = REGR_M1  # gleiche Regressoren, andere AV
    df_m5_prep = df[["log_forks"] + REGR_M5].dropna()
    y5 = df_m5_prep["log_forks"]
    X5 = sm.add_constant(df_m5_prep[REGR_M5])
    m5 = sm.OLS(y5, X5).fit(cov_type="HC3")
    log(f"  n = {len(df_m5_prep):,}")
    log(m5.summary().as_text())
    print_interpretation(m5, "M5 (AV=log_forks)")

    # Vergleich Stars vs. Forks
    log("\n--- Vergleich M1 (log_stars) vs. M5 (log_forks) ---")
    log(f"  {'Variable':<20}  {'M1 (Stars)':>12}  {'M5 (Forks)':>12}")
    for nm in ["native_i", "boosted_i", "log_age", "perm_i"]:
        b1 = m1_hc3.params[nm]; b5 = m5.params[nm]
        log(f"  {nm:<20}  {b1:>+12.4f}  {b5:>+12.4f}")
else:
    log("  ⚠️  Zu wenige Forks-Werte — M5 nicht ausführbar.")
    m5 = None


# ==============================================================================
# INTERAKTIONSPLOT: MARGINALE EFFEKTE (M3b)
# Visualisiert wie der KI-Effekt über verschiedene Contributors-Werte variiert.
# X-Achse: log_contrib_c (zentriert), Y-Achse: vorhergesagte log_stars
# Zwei Linien: ai_i=1 vs. ai_i=0, Controls auf Mittelwert gesetzt.
# ==============================================================================
log(f"\n[{ts()}] Erstelle Interaktionsplot M3b ...")

try:
    # Wertebereich für log_contrib_c (5. bis 95. Perzentil)
    lc_range = np.linspace(
        df["log_contrib_c"].quantile(0.05),
        df["log_contrib_c"].quantile(0.95),
        100
    )
    # Control-Mittelwerte
    ctrl_means = {
        "log_age":     df["log_age"].mean(),
        "org_i":       df["org_i"].mean(),
        "perm_i":      df["perm_i"].mean(),
        "log_commits": df["log_commits"].mean(),
    }

    fig, ax = plt.subplots(figsize=(9, 5))
    for ai_val, label_line, color in [(0, "Non-AI", "#3498DB"), (1, "KI-Projekt", "#E74C3C")]:
        pred_data = pd.DataFrame({
            "const":          1,
            "ai_i":           ai_val,
            "log_contrib_c":  lc_range,
            "ai_x_contrib":   ai_val * lc_range,
            "log_age":        ctrl_means["log_age"],
            "org_i":          ctrl_means["org_i"],
            "perm_i":         ctrl_means["perm_i"],
            "log_commits":    ctrl_means["log_commits"],
        })
        pred_y = m3b.predict(pred_data)
        # X zurücktransformieren für lesbare Achse (Contributors/Monat)
        contrib_raw = np.expm1(lc_range + df["log_contrib"].mean())
        ax.plot(lc_range, pred_y, label=label_line, color=color, linewidth=2.2)

    ax.set_xlabel("log(Contributors/Monat) — zentriert", fontsize=10)
    ax.set_ylabel("Vorhergesagte log(1+Stars)", fontsize=10)
    ax.set_title(
        "Interaktionsplot M3b: KI-Effekt moderiert durch Contributors\n"
        "Controls auf Mittelwert gesetzt",
        fontsize=11, fontweight="bold"
    )
    ax.legend(fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "viz_reg_interactions.png", dpi=150, bbox_inches="tight")
    plt.close()
    log("  → viz_reg_interactions.png gespeichert")
except Exception as e:
    log(f"  ⚠️  Interaktionsplot fehlgeschlagen: {e}")


# ==============================================================================
# VIF-ÜBERSICHTSPLOT
# ==============================================================================
log(f"\n[{ts()}] Erstelle VIF-Übersichtsplot ...")

try:
    vif_data = {
        "M1": vif_m1,
        "M3b (×Contrib)": vif_m3b,
        "M3c (×Alter)": vif_m3c,
        "M3d (×Lizenz)": vif_m3d,
    }
    fig, axes = plt.subplots(1, len(vif_data), figsize=(16, 5), sharey=False)
    for ax, (mname, vif_df) in zip(axes, vif_data.items()):
        colors = ["#E74C3C" if v > 10 else ("#F39C12" if v > 5 else "#2ECC71")
                  for v in vif_df.VIF]
        ax.barh(range(len(vif_df)), vif_df.VIF, color=colors, alpha=0.85)
        ax.set_yticks(range(len(vif_df)))
        ax.set_yticklabels([CLAB.get(v, v) for v in vif_df.Variable], fontsize=8)
        ax.axvline(10, color="#E74C3C", linestyle="--", linewidth=1, label="VIF=10")
        ax.axvline(5,  color="#F39C12", linestyle=":",  linewidth=1, label="VIF=5")
        ax.set_title(mname, fontsize=10, fontweight="bold")
        ax.set_xlabel("VIF", fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    plt.suptitle("VIF-Übersicht: Multikollinearitätsprüfung je Modell",
                 fontsize=12, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "viz_reg_vif.png", dpi=150, bbox_inches="tight")
    plt.close()
    log("  → viz_reg_vif.png gespeichert")
except Exception as e:
    log(f"  ⚠️  VIF-Plot fehlgeschlagen: {e}")


# ==============================================================================
# MODERATOREN-ÜBERSICHTSPLOT (M3b, M3c, M3d nebeneinander)
# ==============================================================================
log(f"\n[{ts()}] Erstelle Moderatoren-Koeffizientenplot ...")

try:
    mod_models = [
        (m3b, "M3b: KI × Contributors"),
        (m3c, "M3c: KI × Alter"),
        (m3d, "M3d: KI × Lizenz"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    for ax, (model, title) in zip(axes, mod_models):
        coefs = model.params.drop("const")
        cis   = model.conf_int().drop("const")
        pvs   = model.pvalues.drop("const")
        ypos  = range(len(coefs))
        cols  = ["#AAAAAA" if p > ALPHA else ("#2ECC71" if c > 0 else "#E74C3C")
                 for c, p in zip(coefs.values, pvs.values)]
        ax.barh(ypos, coefs.values, color=cols, alpha=0.8, height=0.5)
        ax.errorbar(
            coefs.values, ypos,
            xerr=[coefs.values - cis[0].values, cis[1].values - coefs.values],
            fmt="none", color="#222", capsize=4, linewidth=1.3
        )
        ax.axvline(0, color="black", linewidth=1)
        ax.set_yticks(ypos)
        ax.set_yticklabels([CLAB.get(c, c) for c in coefs.index], fontsize=9)
        ax.set_title(title, fontsize=10, fontweight="bold")
        ax.set_xlabel("Koeffizient", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="x", alpha=0.2)
        for i, (c, p, hi) in enumerate(zip(coefs.values, pvs.values, cis[1].values)):
            ax.text(hi + 0.02, i, sig_stars(p), va="center", fontsize=8, color="#555")
    plt.suptitle(
        "Moderationsanalyse: Bedingungen des KI-Popularitätsbonus",
        fontsize=12, fontweight="bold", y=1.01
    )
    plt.tight_layout()
    plt.savefig(OUT_DIR / "viz_reg_m3_moderators.png", dpi=150, bbox_inches="tight")
    plt.close()
    log("  → viz_reg_m3_moderators.png gespeichert")
except Exception as e:
    log(f"  ⚠️  Moderatoren-Plot fehlgeschlagen: {e}")


# ==============================================================================
# PAPER-READY REGRESSIONSTABELLE
# Alle Modelle in einer Tabelle: Koef*** (SE)
# ==============================================================================
log(f"\n{'='*70}")
log("PAPER-READY REGRESSIONSTABELLE")

models_for_table = {
    "M1 HC3":         m1_hc3,
    "M2 Clustered":   m2_cl,
    "M3a ai_i":       m3a,
    "M3b ×Contrib":   m3b,
    "M3c ×Alter":     m3c,
    "M3d ×Lizenz":    m3d,
    "M4 (no_commits)": m4,
}
if m5 is not None:
    models_for_table["M5 (Forks AV)"] = m5

tab = make_results_table(models_for_table)


# ==============================================================================
# ZUSAMMENFASSUNG DER ERGEBNISSE
# ==============================================================================
log(f"\n{'='*70}")
log("ZUSAMMENFASSUNG ALLER HYPOTHESENTESTS")
log(f"  {'Hypothese':<8}  {'Test':<35}  {'Ergebnis':<12}  {'Koeffizient'}")
log(f"  {'-'*80}")

hyps = [
    ("H1", "native_i > 0 (AI-Born > Non-AI)",       m1_hc3, "native_i"),
    ("H2", "boosted_i > 0 (AI-Boosted > Non-AI)",   m1_hc3, "boosted_i"),
    ("H4", "ai_x_contrib > 0 (Mod. Contributors)",  m3b,    "ai_x_contrib"),
    ("H5", "ai_x_age < 0 (Mod. Alter)",             m3c,    "ai_x_age"),
    ("H6", "ai_x_perm > 0 (Mod. Lizenz)",           m3d,    "ai_x_perm"),
]

for hyp, desc, model, var in hyps:
    b = model.params[var]
    p = model.pvalues[var]
    result = "BESTÄTIGT" if p < ALPHA else "NICHT BEST."
    log(f"  {hyp:<8}  {desc:<35}  {result:<12}  β={b:+.4f} {sig_stars(p)}")

log(f"\n  H3 (Wald-Test native=boosted): p={wald_p:.4f}  → "
    f"{'H3 abgelehnt: getrennte Dummies' if wald_p < ALPHA else 'H3 nicht abgelehnt: kombinierter ai_i berechtigt'}")

log(f"\n  R² Hauptmodell M1: {m1_hc3.rsquared:.4f}")
log(f"  n Hauptmodell M1:  {int(m1_hc3.nobs):,}")

# ==============================================================================
# LOG SPEICHERN
# ==============================================================================
save_log()
log(f"\n[{ts()}] Fertig. Alle Outputs in: {OUT_DIR}")
