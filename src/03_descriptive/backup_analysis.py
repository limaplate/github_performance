"""
backup_analysis.py — Zusatzanalysen fuer Prof-Meeting

Block 0: Feld-Exploration (automatisch beim Start)
Block 1: Organisation vs. Einzelperson — Bar Chart (viz_18)
Block 2: Stars / Popularitaet — Event Study oder Querschnitt (viz_19)
Block 3: Lizenz-Verteilung — Permissiv vs. Copyleft (viz_20)

Voraussetzung: ki_repo_mapping.json + event_study_results.json
"""

import json, sys, time
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
from pymongo import MongoClient
import statistics

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.db_config import get_mongo_uri
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.paths import get_output_dir

MONGO_URI = get_mongo_uri()
DB_NAME = "upstreamPackages"
OUT_DIR = get_output_dir()
OUT_JSON = OUT_DIR / "backup_analysis_results.json"

for _p in [
    Path(__file__).parent / "ki_repo_mapping.json",
    Path("/Users/lmpl/Desktop/Bachelorarbeit/Analyse/ki_repo_mapping.json"),
    Path("/Users/lmpl/Desktop/Bachelorarbeit/ki_repo_mapping.json"),
]:
    if _p.exists():
        KI_MAPPING_PATH = _p
        break
else:
    raise FileNotFoundError("ki_repo_mapping.json nicht gefunden")

for _p in [
    Path(__file__).parent / "event_study_results.json",
    Path("/Users/lmpl/Desktop/Bachelorarbeit/Analyse/event_study_results.json"),
]:
    if _p.exists():
        ES_RESULTS_PATH = _p
        break
else:
    ES_RESULTS_PATH = None

PERMISSIVE_SPDX = {
    "MIT", "Apache-2.0", "Apache-1.1",
    "BSD-2-Clause", "BSD-3-Clause", "BSD-3-Clause-Clear", "BSD-4-Clause",
    "ISC", "0BSD", "Unlicense", "CC0-1.0", "WTFPL",
    "PSF-2.0", "Python-2.0", "Zlib",
    "LGPL-2.0", "LGPL-2.1", "LGPL-2.1-only", "LGPL-2.1-or-later",
    "LGPL-3.0", "LGPL-3.0-only", "LGPL-3.0-or-later",
    "MPL-2.0",
}
COPYLEFT_SPDX = {
    "GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-2.0+",
    "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later", "GPL-3.0+",
    "AGPL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later",
    "EUPL-1.1", "EUPL-1.2", "CC-BY-SA-4.0",
}


def ts():
    return datetime.now().strftime("%H:%M:%S")


def classify_license(spdx_str):
    if not spdx_str:
        return "Andere"
    s = str(spdx_str).strip()
    sl = s.lower()

    if sl in ("noassertion", "unknown", "none", "other", "non-standard", ""):
        return "Andere"

    # Exakter SPDX-Match
    if s in PERMISSIVE_SPDX:
        return "Permissiv"
    if s in COPYLEFT_SPDX:
        return "Copyleft"

    # Freitext → Permissiv (GitHub-Vollnamen und Varianten)
    PERMISSIVE_PATTERNS = [
        "mit license", "mit no attribution",
        "apache license", "apache-2",
        "bsd 2-clause", "bsd 3-clause", "bsd 4-clause",
        "isc license",
        "the unlicense",
        "creative commons zero", "cc0",
        "do what the f",                        # WTFPL
        "boost software license",
        "mozilla public license",
        "lesser general public license",        # LGPL (alle Versionen)
        "gnu lesser",
        "universal permissive license",
        "python software foundation",
        "artistic license",
        "zlib",
        # Kurzformen
        "mit", "apache", "isc", "unlicense", "wtfpl", "mpl",
        "lgpl", "bsd",
    ]
    COPYLEFT_PATTERNS = [
        "gnu general public license",
        "gnu affero general public license",
        "european union public license",
        "creative commons attribution share alike",  # CC-BY-SA
        # Kurzformen
        "gpl", "agpl", "eupl",
    ]

    for p in PERMISSIVE_PATTERNS:
        if p in sl:
            return "Permissiv"
    for c in COPYLEFT_PATTERNS:
        if c in sl:
            return "Copyleft"

    # Creative Commons BY (ohne SA) → Andere (nicht für Software gedacht)
    if "creative commons" in sl:
        return "Andere"

    return "Andere"


def extract_license_str(pi_doc):
    """Extrahiert SPDX-String aus packageInformation."""
    if not pi_doc:
        return None
    for field in ["license", "licenses", "licenseInfo", "spdxId"]:
        val = pi_doc.get(field)
        if val:
            if isinstance(val, str):
                return val
            if isinstance(val, list) and val:
                v = val[0]
                return v if isinstance(v, str) else (v.get("spdxId") or v.get("name"))
            if isinstance(val, dict):
                return val.get("spdxId") or val.get("name") or val.get("id")
    for proj in pi_doc.get("projects", []):
        for field in ["licenseInfo", "license", "spdxId"]:
            val = proj.get(field)
            if val:
                if isinstance(val, str):
                    return val
                if isinstance(val, dict):
                    return val.get("spdxId") or val.get("name")
    return None


def date_to_ym(dt):
    if isinstance(dt, datetime):
        return (dt.year, dt.month)
    if isinstance(dt, int):
        return date_to_ym(datetime.utcfromtimestamp(dt))
    return None


def ym_diff(ym1, ym2):
    return (ym1[0] - ym2[0]) * 12 + (ym1[1] - ym2[1])


def main():
    print(f"[{ts()}] Lade KI-Repo-Mapping...")
    with open(KI_MAPPING_PATH, encoding="utf-8") as f:
        ki_data = json.load(f)

    ki_mapping    = ki_data.get("repo_mapping", {})
    native_repos  = {r for r, d in ki_mapping.items() if d.get("ki_type") == "native"}
    boosted_repos = {r for r, d in ki_mapping.items() if d.get("ki_type") == "boosted"}
    print(f"  AI-native:  {len(native_repos):,}")
    print(f"  AI-boosted: {len(boosted_repos):,}")

    print(f"\n[{ts()}] Verbinde mit MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]
    db.command("ping")
    print(f"[{ts()}] Verbunden.\n")

    pkg_col      = db["depsPackages"]
    panel_col    = db["depsProjectsPanel"]
    projects_col = db["depsProjects"]   # statische Repo-Metadaten inkl. ownerData

    results = {}
    BATCH = 300

    # ── Block 0: Kurze Feld-Bestätigung + Lizenz-Rohwerte ────────────────────
    print(f"[{ts()}] Block 0: Prüfe depsProjects...")
    sample_dp = projects_col.find_one(
        {"name": {"$in": list(native_repos)[:50]}}
    )
    if sample_dp:
        print(f"  depsProjects Felder: {[k for k in sample_dp.keys() if k != '_id']}")
        od = sample_dp.get("ownerData", {})
        print(f"  ownerData.type Beispiel: {od.get('type')} ({sample_dp.get('name')})")
    else:
        print("  WARNUNG: depsProjects — keine KI-Repos gefunden, prüfe Collection-Namen")

    all_repos_lower = [r.lower() for r in list(native_repos) + list(boosted_repos)]
    lic_counts = Counter()
    for doc in projects_col.find(
        {"name": {"$in": all_repos_lower}},
        {"repoData.license": 1, "license": 1}
    ):
        v = doc.get("repoData", {}).get("license") or doc.get("license") or "NONE"
        lic_counts[str(v)] += 1
    print(f"\n  Top-40 Lizenz-Rohwerte in depsProjects:")
    for lic, n in lic_counts.most_common(40):
        print(f"    {n:>6}  {lic}")

    # ── Block 1: Organisation vs. Einzelperson ────────────────────────────────
    print(f"\n[{ts()}] Block 1: Organisation vs. Einzelperson (ownerData.type aus depsProjects)...")

    org_data = {}
    for ki_type, repo_set in [("native", native_repos), ("boosted", boosted_repos)]:
        counts   = Counter()
        repo_list = list(repo_set)
        for i in range(0, len(repo_list), BATCH):
            batch = repo_list[i:i+BATCH]
            # name-Feld in depsProjects ist lowercase owner/repo
            docs = projects_col.find(
                {"name": {"$in": [r.lower() for r in batch]}},
                {"name": 1, "ownerData.type": 1}
            )
            for doc in docs:
                owner_type = doc.get("ownerData", {}).get("type", "")
                label = "Organisation" if owner_type == "Organization" else "Einzelperson"
                counts[label] += 1
        org_data[ki_type] = dict(counts)
        print(f"  {ki_type}: {org_data[ki_type]}")

    results["org_data"] = org_data

    # ── Block 2: Stars ────────────────────────────────────────────────────────
    print(f"\n[{ts()}] Block 2: Stars-Analyse (repoData.stars aus depsProjects)...")

    nat_stars, boo_stars = [], []
    for ki_type, repo_set, target in [
        ("native",  native_repos,  nat_stars),
        ("boosted", boosted_repos, boo_stars),
    ]:
        repo_list = list(repo_set)
        for i in range(0, len(repo_list), BATCH):
            batch = [r.lower() for r in repo_list[i:i+BATCH]]
            docs = projects_col.find(
                {"name": {"$in": batch}},
                {"repoData.stars": 1, "stars": 1}
            )
            for doc in docs:
                # repoData.stars bevorzugen, Fallback auf top-level stars
                v = doc.get("repoData", {}).get("stars")
                if v is None:
                    v = doc.get("stars")
                if isinstance(v, (int, float)):
                    target.append(int(v))

        med = statistics.median(target) if target else 0
        print(f"  {ki_type}: n={len(target):,}, Median={med:.0f}")

    stars_result = {
        "mode":           "static",
        "native":         {"values": sorted(nat_stars)},
        "boosted":        {"values": sorted(boo_stars)},
        "native_median":  statistics.median(nat_stars)  if nat_stars  else 0,
        "boosted_median": statistics.median(boo_stars)  if boo_stars  else 0,
    }
    results["stars"] = stars_result

    # ── Block 3: Lizenz ────────────────────────────────────────────────────────
    print(f"\n[{ts()}] Block 3: Lizenz-Analyse (repoData.license aus depsProjects)...")

    lic_data = {"native": Counter(), "boosted": Counter()}

    for ki_type, repo_set in [("native", native_repos), ("boosted", boosted_repos)]:
        repo_list = list(repo_set)
        for i in range(0, len(repo_list), BATCH):
            batch = [r.lower() for r in repo_list[i:i+BATCH]]
            docs = projects_col.find(
                {"name": {"$in": batch}},
                {"repoData.license": 1, "license": 1}
            )
            for doc in docs:
                # repoData.license bevorzugen, Fallback auf top-level license
                spdx = doc.get("repoData", {}).get("license")
                if not spdx:
                    spdx = doc.get("license")
                lic_data[ki_type][classify_license(spdx)] += 1

        print(f"  {ki_type}: {dict(lic_data[ki_type])}")

    results["license_data"] = {k: dict(v) for k, v in lic_data.items()}

    # ── Plots ──────────────────────────────────────────────────────────────────
    print(f"\n[{ts()}] Generiere Plots...")
    _draw_plots(org_data, stars_result, lic_data, OUT_DIR)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Ergebnisse: {OUT_JSON}")
    client.close()
    print(f"\n[{ts()}] Fertig.")


# ── Plot-Funktionen ────────────────────────────────────────────────────────────

def _draw_plots(org_data, stars_result, lic_data, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib as mpl
    import numpy as np
    mpl.rcParams["font.family"] = "DejaVu Sans"

    COLOR_NATIVE  = "#1E8449"
    COLOR_BOOSTED = "#E67E22"
    COLOR_ANNO    = "#1A1A2E"
    COLOR_EVENT   = "#E74C3C"
    COLOR_REF     = "#AAAAAA"

    def safe(lst):
        return [v if v is not None else float("nan") for v in lst]

    # ── viz_18: Organisation vs. Einzelperson ─────────────────────────────────
    all_cats = sorted(
        set(list(org_data.get("native", {}).keys()) + list(org_data.get("boosted", {}).keys())),
        key=lambda x: (x != "Organisation", x)
    )
    n_nat = max(sum(org_data.get("native",  {}).values()), 1)
    n_boo = max(sum(org_data.get("boosted", {}).values()), 1)

    pct_nat = [100 * org_data.get("native",  {}).get(c, 0) / n_nat for c in all_cats]
    pct_boo = [100 * org_data.get("boosted", {}).get(c, 0) / n_boo for c in all_cats]

    x     = np.arange(len(all_cats))
    width = 0.33

    fig, ax = plt.subplots(figsize=(max(9, len(all_cats)*3), 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    bars_nat = ax.bar(x - width/2, pct_nat, width,
                      color=COLOR_NATIVE, alpha=0.85, label=f"AI-native (n={n_nat:,})")
    bars_boo = ax.bar(x + width/2, pct_boo, width,
                      color=COLOR_BOOSTED, alpha=0.85, label=f"AI-boosted (n={n_boo:,})")

    for bar, val in zip(bars_nat, pct_nat):
        if val > 0.5:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
                    f"{val:.1f}%", ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color=COLOR_NATIVE)
    for bar, val in zip(bars_boo, pct_boo):
        if val > 0.5:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
                    f"{val:.1f}%", ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color=COLOR_BOOSTED)

    ax.set_xticks(x)
    ax.set_xticklabels(all_cats, fontsize=12)
    ax.set_ylabel("Anteil (%)", fontsize=11)
    ax.set_ylim(0, max(max(pct_nat + [0]), max(pct_boo + [0])) * 1.18 + 5)
    ax.set_title(
        "Eigentümerstruktur: AI-native vs. AI-boosted Repositories\n"
        "GitHub-Organisations-Account vs. persönlicher Nutzer-Account",
        fontsize=12, fontweight="bold", color=COLOR_ANNO, pad=12
    )
    ax.legend(fontsize=10, framealpha=0.9)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)

    fig.text(0.5, -0.02,
        "Klassifikation: Owner mit ≥3 Repositories im KI-Datensatz = Organisation; sonst Einzelperson/unbekannt.",
        fontsize=8.5, ha="center", color="#666666", style="italic",
        bbox=dict(boxstyle="round,pad=0.3", fc="#F9F9F9", ec="#CCCCCC", lw=0.7))

    plt.tight_layout(rect=[0, 0.06, 1, 1])
    out = Path(out_dir) / "viz_18_org_vs_nutzer.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Gespeichert: {out.name}")

    # ── viz_19: Stars ─────────────────────────────────────────────────────────
    mode = stars_result.get("mode", "unavailable")

    if mode == "event_study":
        t_range = stars_result["t_range"]
        t_pos   = stars_result["t_pos"]
        xs_b    = t_range
        xs_n    = t_pos
        bc = stars_result["boosted"]
        nc = stars_result["native"]
        n_b = stars_result["n_boosted"]
        n_n = stars_result["n_native"]

        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        fig.patch.set_facecolor("white")
        fig.suptitle(
            "GitHub Stars als Erfolgsindikator: AI-boosted vs. AI-native\n"
            "Normiert auf Referenzmonat = 1.0 | Median der per-Repo-Ratios",
            fontsize=12, fontweight="bold", color=COLOR_ANNO
        )

        for ax, xs, c, title, ylabel, ref_label, n, color in [
            (axes[0], xs_b, bc, "Stars — AI-boosted", "Stars-Ratio (t=−1 = 1.0)",
             "t = 0\nKI-Adoption", n_b, COLOR_BOOSTED),
            (axes[1], xs_n, nc, "Stars — AI-native",  "Stars-Ratio (t=0 = 1.0)",
             "t = 0\nGründung",   n_n, COLOR_NATIVE),
        ]:
            ax.set_facecolor("white")
            ax.fill_between(xs, safe(c["q25"]), safe(c["q75"]),
                            alpha=0.20, color=color)
            ax.plot(xs, safe(c["median"]), color=color, linewidth=2.5,
                    label=f"Median (n≈{n:,})")
            ax.axvline(0, color=COLOR_EVENT, linewidth=2, alpha=0.85, zorder=4)
            ax.axhline(1.0, color=COLOR_REF, linewidth=1, linestyle=":", zorder=1)
            ylim = ax.get_ylim()
            ax.text(0.4, ylim[1] - (ylim[1]-ylim[0])*0.05,
                    ref_label, fontsize=8.5, color=COLOR_EVENT, va="top")
            ax.set_xlabel("Monate relativ zu t=0", fontsize=10)
            ax.set_ylabel(ylabel, fontsize=10)
            ax.set_title(title, fontsize=11, fontweight="bold")
            ax.grid(axis="both", linestyle="--", alpha=0.3)
            ax.spines[["top", "right"]].set_visible(False)
            ax.legend(fontsize=9, framealpha=0.9)

        axes[0].set_xticks(range(-24, 25, 6))
        axes[1].set_xticks(range(0, 25, 3))

        plt.tight_layout(rect=[0, 0, 1, 0.92])
        out = Path(out_dir) / "viz_19_stars_event_study.png"

    elif mode == "static" and "values" in stars_result.get("native", {}):
        nat_vals = stars_result["native"]["values"]
        boo_vals = stars_result["boosted"]["values"]
        n_nat_m  = stars_result["native_median"]
        n_boo_m  = stars_result["boosted_median"]

        import numpy as np

        def pct(vals, p):
            if not vals:
                return 0
            s = sorted(vals)
            return s[max(0, min(int(len(s) * p / 100), len(s) - 1))]

        # Perzentil-Balken: Median + Q25/Q75 als Fehlerbalken + Beschriftungen
        groups   = ["AI-native", "AI-boosted"]
        medians  = [n_nat_m, n_boo_m]
        q25s     = [pct(nat_vals, 25), pct(boo_vals, 25)]
        q75s     = [pct(nat_vals, 75), pct(boo_vals, 75)]
        p90s     = [pct(nat_vals, 90), pct(boo_vals, 90)]
        colors   = [COLOR_NATIVE, COLOR_BOOSTED]
        ns       = [len(nat_vals), len(boo_vals)]

        err_low  = [max(0, m - q) for m, q in zip(medians, q25s)]
        err_high = [max(0, q - m) for m, q in zip(q75s, medians)]

        fig, axes_s = plt.subplots(1, 2, figsize=(13, 6),
                                   gridspec_kw={"width_ratios": [1, 1.6]})
        fig.patch.set_facecolor("white")
        fig.suptitle(
            "GitHub Stars: AI-native vs. AI-boosted\n"
            "AI-boosted Repos haben fast doppelt so viele Stars — sie sind ältere, etabliertere Projekte",
            fontsize=12, fontweight="bold", color=COLOR_ANNO
        )

        # Linkes Panel: Median-Balken mit IQR-Fehlerbalken
        ax_l = axes_s[0]
        ax_l.set_facecolor("white")
        x = np.arange(len(groups))
        bars = ax_l.bar(x, medians, width=0.45, color=colors, alpha=0.85,
                        edgecolor="white", linewidth=1.5)
        ax_l.errorbar(x, medians,
                      yerr=[err_low, err_high],
                      fmt="none", color="#333333", capsize=8, capthick=2, linewidth=2)

        for i, (bar, med, q25, q75, p90, n) in enumerate(
                zip(bars, medians, q25s, q75s, p90s, ns)):
            ax_l.text(bar.get_x() + bar.get_width()/2,
                      q75 + max(medians) * 0.06,
                      f"Median: {med:.0f}\nIQR: {q25:.0f}–{q75:.0f}",
                      ha="center", va="bottom", fontsize=9.5, fontweight="bold",
                      color=colors[i])
            ax_l.text(bar.get_x() + bar.get_width()/2, -max(medians) * 0.12,
                      f"n = {n:,}", ha="center", va="top",
                      fontsize=8.5, color="#666666")

        ax_l.set_xticks(x)
        ax_l.set_xticklabels(groups, fontsize=12)
        ax_l.set_ylabel("GitHub Stars (Median)", fontsize=10)
        ax_l.set_ylim(-max(medians) * 0.18, max(q75s) * 1.55)
        ax_l.set_title("Median + IQR", fontsize=11, fontweight="bold")
        ax_l.grid(axis="y", linestyle="--", alpha=0.3)
        ax_l.spines[["top", "right"]].set_visible(False)

        # Rechtes Panel: Perzentil-Profil (zeigt die schiefe Verteilung)
        ax_r = axes_s[1]
        ax_r.set_facecolor("white")
        pct_levels = [10, 25, 50, 75, 90, 95]
        nat_pcts = [pct(nat_vals, p) for p in pct_levels]
        boo_pcts = [pct(boo_vals, p) for p in pct_levels]

        ax_r.plot(pct_levels, nat_pcts, color=COLOR_NATIVE, linewidth=2.5,
                  marker="o", markersize=6, label=f"AI-native (n={ns[0]:,})")
        ax_r.plot(pct_levels, boo_pcts, color=COLOR_BOOSTED, linewidth=2.5,
                  marker="s", markersize=6, label=f"AI-boosted (n={ns[1]:,})")

        ax_r.fill_between(pct_levels, nat_pcts, boo_pcts,
                          alpha=0.10, color=COLOR_BOOSTED)

        for p, nv, bv in zip(pct_levels, nat_pcts, boo_pcts):
            ax_r.text(p, nv - max(nat_pcts)*0.04, f"{nv:.0f}",
                      ha="center", va="top", fontsize=7.5, color=COLOR_NATIVE)
            ax_r.text(p, bv + max(boo_pcts)*0.02, f"{bv:.0f}",
                      ha="center", va="bottom", fontsize=7.5, color=COLOR_BOOSTED)

        ax_r.set_xlabel("Perzentil", fontsize=10)
        ax_r.set_ylabel("GitHub Stars", fontsize=10)
        ax_r.set_title("Verteilungsprofil nach Perzentilen", fontsize=11, fontweight="bold")
        ax_r.set_xticks(pct_levels)
        ax_r.set_xticklabels([f"P{p}" for p in pct_levels], fontsize=9)
        ax_r.grid(axis="both", linestyle="--", alpha=0.3)
        ax_r.spines[["top", "right"]].set_visible(False)
        ax_r.legend(fontsize=9.5, framealpha=0.9)

        fig.text(
            0.5, -0.03,
            "Lesehilfe: AI-boosted Repos existierten bereits vor ihrer KI-Adoption und haben "
            "daher mehr Zeit gehabt, eine Community aufzubauen. "
            "Die höhere Star-Zahl spiegelt Projektreife wider, nicht KI-Erfolg.",
            fontsize=8.5, ha="center", color="#555555", style="italic",
            bbox=dict(boxstyle="round,pad=0.4", fc="#F9F9F9", ec="#CCCCCC", lw=0.7)
        )

        plt.tight_layout(rect=[0, 0.07, 1, 0.92])
        out = Path(out_dir) / "viz_19_stars_querschnitt.png"

    else:
        print("  Stars: keine Daten — viz_19 übersprungen.")
        out = None

    if out:
        plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close()
        print(f"  Gespeichert: {out.name}")

    # ── viz_20: Lizenz-Verteilung ─────────────────────────────────────────────
    LIC_CATS   = ["Permissiv", "Copyleft", "Andere"]
    LIC_COLORS = ["#2ECC71", "#E74C3C", "#95A5A6"]

    n_nat_l = max(sum(lic_data["native"].values()),  1)
    n_boo_l = max(sum(lic_data["boosted"].values()), 1)

    pct_nat_l = [100 * lic_data["native"].get(c,  0) / n_nat_l for c in LIC_CATS]
    pct_boo_l = [100 * lic_data["boosted"].get(c, 0) / n_boo_l for c in LIC_CATS]

    fig, axes20 = plt.subplots(1, 2, figsize=(14, 6))
    fig.patch.set_facecolor("white")
    fig.suptitle(
        "Lizenz-Verteilung: AI-native vs. AI-boosted Repositories\n"
        "Permissiv (MIT, Apache, BSD, ...) vs. Copyleft (GPL, AGPL, ...)",
        fontsize=12, fontweight="bold", color=COLOR_ANNO
    )

    for ax, pct, title, n, color in [
        (axes20[0], pct_nat_l, "AI-native",  n_nat_l, COLOR_NATIVE),
        (axes20[1], pct_boo_l, "AI-boosted", n_boo_l, COLOR_BOOSTED),
    ]:
        ax.set_facecolor("white")
        bars = ax.bar(LIC_CATS, pct, color=LIC_COLORS, alpha=0.88,
                      edgecolor="white", linewidth=1.5)
        for bar, val in zip(bars, pct):
            if val > 1:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.6,
                        f"{val:.1f}%", ha="center", va="bottom",
                        fontsize=10, fontweight="bold")
        ax.set_ylabel("Anteil (%)", fontsize=10)
        ax.set_ylim(0, max(pct)*1.18 + 4)
        ax.set_title(f"{title} (n={n:,})", fontsize=11, fontweight="bold", color=color)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="x", labelsize=9)

    lic_handles = [
        mpatches.Patch(color=LIC_COLORS[0], alpha=0.85,
                       label="Permissiv — MIT, Apache-2.0, BSD, ISC, ..."),
        mpatches.Patch(color=LIC_COLORS[1], alpha=0.85,
                       label="Copyleft — GPL-2.0/3.0, AGPL-3.0, ..."),
        mpatches.Patch(color=LIC_COLORS[2], alpha=0.85,
                       label="Andere — proprietär, unbekannt, kein Eintrag"),
    ]
    fig.legend(handles=lic_handles, loc="lower center", ncol=3,
               fontsize=9, framealpha=0.9, bbox_to_anchor=(0.5, -0.06))

    plt.tight_layout(rect=[0, 0.1, 1, 0.92])
    out = Path(out_dir) / "viz_20_lizenz.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Gespeichert: {out.name}")


if __name__ == "__main__":
    import sys
    if "--plots-only" in sys.argv:
        with open(OUT_JSON, encoding="utf-8") as f:
            saved = json.load(f)
        org_data   = saved.get("org_data", {})
        stars_res  = saved.get("stars", {"mode": "unavailable"})
        lic_raw    = saved.get("license_data", {})
        lic_data   = {k: Counter(v) for k, v in lic_raw.items()}
        print("Regeneriere Plots aus gespeichertem JSON...")
        _draw_plots(org_data, stars_res, lic_data, OUT_DIR)
        print("Fertig.")
    else:
        main()
