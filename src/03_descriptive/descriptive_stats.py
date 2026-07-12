"""
descriptive_stats.py — Deskriptive Querschnittsanalysen

Block 1: Organisation vs. Einzelperson (viz_18)
Block 2: Stars-Verteilung nach Gruppe (viz_19)
Block 3: Lizenz-Verteilung (viz_20)

Gruppen: non_ai, native, boosted
Voraussetzung: ki_repo_mapping.json (aus build_ki_repo_mapping.py)

Output:
  descriptive_stats_results.json
  viz_18_org_vs_nutzer.png
  viz_19_stars_querschnitt.png
  viz_20_lizenz.png
"""

import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from pymongo import MongoClient
import statistics

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.db_config import get_mongo_uri
from common.paths import get_output_dir

import argparse as _argparse
_p = _argparse.ArgumentParser(add_help=False)
_args, _ = _p.parse_known_args()

MONGO_URI = get_mongo_uri()
DB_NAME = "upstreamPackagesV2"
OUT_DIR   = get_output_dir()
OUT_JSON  = OUT_DIR / "descriptive_stats_results.json"
KI_MAPPING_PATH = OUT_DIR / "ki_repo_mapping.json"

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
    s  = str(spdx_str).strip()
    sl = s.lower()
    if sl in ("noassertion", "unknown", "none", "other", "non-standard", ""):
        return "Andere"
    if s in PERMISSIVE_SPDX:
        return "Permissiv"
    if s in COPYLEFT_SPDX:
        return "Copyleft"
    PERMISSIVE_PATTERNS = [
        "mit license", "mit no attribution", "apache license", "apache-2",
        "bsd 2-clause", "bsd 3-clause", "bsd 4-clause", "isc license",
        "the unlicense", "creative commons zero", "cc0", "do what the f",
        "boost software license", "mozilla public license",
        "lesser general public license", "gnu lesser",
        "universal permissive license", "python software foundation",
        "artistic license", "zlib", "mit", "apache", "isc", "unlicense",
        "wtfpl", "mpl", "lgpl", "bsd",
    ]
    COPYLEFT_PATTERNS = [
        "gnu general public license", "gnu affero general public license",
        "european union public license",
        "creative commons attribution share alike",
        "gpl", "agpl", "eupl",
    ]
    for p in PERMISSIVE_PATTERNS:
        if p in sl:
            return "Permissiv"
    for c in COPYLEFT_PATTERNS:
        if c in sl:
            return "Copyleft"
    if "creative commons" in sl:
        return "Andere"
    return "Andere"


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

    projects_col = db["depsProjects"]
    results = {}
    BATCH = 300

    # ── Block 1: Organisation vs. Einzelperson ────────────────────────────────
    print(f"[{ts()}] Block 1: Organisation vs. Einzelperson...")
    org_data = {}
    for ki_type, repo_set in [("native", native_repos), ("boosted", boosted_repos)]:
        counts    = Counter()
        repo_list = list(repo_set)
        for i in range(0, len(repo_list), BATCH):
            batch = repo_list[i:i+BATCH]
            docs  = projects_col.find(
                {"_id.name": {"$in": batch}},
                {"ownerData.type": 1}
            )
            for doc in docs:
                owner_type = doc.get("ownerData", {}).get("type", "")
                label = "Organisation" if owner_type == "Organization" else "Einzelperson"
                counts[label] += 1
        org_data[ki_type] = dict(counts)
        print(f"  {ki_type}: {org_data[ki_type]}")
    results["org_data"] = org_data

    # ── Block 2: Stars ────────────────────────────────────────────────────────
    print(f"\n[{ts()}] Block 2: Stars-Analyse...")
    nat_stars, boo_stars = [], []
    for ki_type, repo_set, target in [
        ("native",  native_repos,  nat_stars),
        ("boosted", boosted_repos, boo_stars),
    ]:
        repo_list = list(repo_set)
        for i in range(0, len(repo_list), BATCH):
            batch = repo_list[i:i+BATCH]
            docs  = projects_col.find(
                {"_id.name": {"$in": batch}},
                {"repoData.stars": 1, "stars": 1}
            )
            for doc in docs:
                v = doc.get("repoData", {}).get("stars")
                if v is None:
                    v = doc.get("stars")
                if isinstance(v, (int, float)):
                    target.append(int(v))
        med = statistics.median(target) if target else 0
        avg = sum(target) / len(target) if target else 0
        print(f"  {ki_type}: n={len(target):,}, Median={med:.0f}, Mittelwert={avg:.0f}")

    results["stars"] = {
        "mode":           "static",
        "native":         {"values": sorted(nat_stars)},
        "boosted":        {"values": sorted(boo_stars)},
        "native_median":  statistics.median(nat_stars)  if nat_stars  else 0,
        "boosted_median": statistics.median(boo_stars)  if boo_stars  else 0,
        "native_mean":    sum(nat_stars) / len(nat_stars)   if nat_stars  else 0,
        "boosted_mean":   sum(boo_stars) / len(boo_stars)   if boo_stars  else 0,
    }

    # ── Block 3: Lizenz ────────────────────────────────────────────────────────
    print(f"\n[{ts()}] Block 3: Lizenz-Analyse...")
    lic_data = {"native": Counter(), "boosted": Counter()}
    for ki_type, repo_set in [("native", native_repos), ("boosted", boosted_repos)]:
        repo_list = list(repo_set)
        for i in range(0, len(repo_list), BATCH):
            batch = repo_list[i:i+BATCH]
            docs  = projects_col.find(
                {"_id.name": {"$in": batch}},
                {"repoData.license": 1, "license": 1}
            )
            for doc in docs:
                spdx = doc.get("repoData", {}).get("license")
                if not spdx:
                    spdx = doc.get("license")
                lic_data[ki_type][classify_license(spdx)] += 1
        print(f"  {ki_type}: {dict(lic_data[ki_type])}")
    results["license_data"] = {k: dict(v) for k, v in lic_data.items()}

    # ── Plots ──────────────────────────────────────────────────────────────────
    print(f"\n[{ts()}] Generiere Plots...")
    _draw_plots(org_data, results["stars"], lic_data, OUT_DIR)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Ergebnisse: {OUT_JSON}")
    client.close()
    print(f"\n[{ts()}] Fertig.")


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
    plt.tight_layout()
    out = Path(out_dir) / "viz_18_org_vs_nutzer.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Gespeichert: {out.name}")

    # ── viz_19: Stars ─────────────────────────────────────────────────────────
    nat_vals = stars_result["native"]["values"]
    boo_vals = stars_result["boosted"]["values"]
    n_nat_m  = stars_result["native_median"]
    n_boo_m  = stars_result["boosted_median"]

    def pct_val(vals, p):
        if not vals:
            return 0
        s = sorted(vals)
        return s[max(0, min(int(len(s) * p / 100), len(s) - 1))]

    groups  = ["AI-native", "AI-boosted"]
    medians = [n_nat_m, n_boo_m]
    q25s    = [pct_val(nat_vals, 25), pct_val(boo_vals, 25)]
    q75s    = [pct_val(nat_vals, 75), pct_val(boo_vals, 75)]
    colors  = [COLOR_NATIVE, COLOR_BOOSTED]
    ns      = [len(nat_vals), len(boo_vals)]
    err_low  = [max(0, m - q) for m, q in zip(medians, q25s)]
    err_high = [max(0, q - m) for m, q in zip(q75s, medians)]

    fig, axes_s = plt.subplots(1, 2, figsize=(13, 6),
                               gridspec_kw={"width_ratios": [1, 1.6]})
    fig.patch.set_facecolor("white")
    fig.suptitle(
        "GitHub Stars: AI-native vs. AI-boosted",
        fontsize=12, fontweight="bold", color=COLOR_ANNO
    )
    ax_l = axes_s[0]
    ax_l.set_facecolor("white")
    x    = np.arange(len(groups))
    bars = ax_l.bar(x, medians, width=0.45, color=colors, alpha=0.85,
                    edgecolor="white", linewidth=1.5)
    ax_l.errorbar(x, medians, yerr=[err_low, err_high],
                  fmt="none", color="#333333", capsize=8, capthick=2, linewidth=2)
    for i, (bar, med, q25, q75, n) in enumerate(zip(bars, medians, q25s, q75s, ns)):
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

    ax_r = axes_s[1]
    ax_r.set_facecolor("white")
    pct_levels = [10, 25, 50, 75, 90, 95]
    nat_pcts   = [pct_val(nat_vals, p) for p in pct_levels]
    boo_pcts   = [pct_val(boo_vals, p) for p in pct_levels]
    ax_r.plot(pct_levels, nat_pcts, color=COLOR_NATIVE, linewidth=2.5,
              marker="o", markersize=6, label=f"AI-native (n={ns[0]:,})")
    ax_r.plot(pct_levels, boo_pcts, color=COLOR_BOOSTED, linewidth=2.5,
              marker="s", markersize=6, label=f"AI-boosted (n={ns[1]:,})")
    ax_r.fill_between(pct_levels, nat_pcts, boo_pcts, alpha=0.10, color=COLOR_BOOSTED)
    ax_r.set_xlabel("Perzentil", fontsize=10)
    ax_r.set_ylabel("GitHub Stars", fontsize=10)
    ax_r.set_title("Verteilungsprofil nach Perzentilen", fontsize=11, fontweight="bold")
    ax_r.set_xticks(pct_levels)
    ax_r.set_xticklabels([f"P{p}" for p in pct_levels], fontsize=9)
    ax_r.grid(axis="both", linestyle="--", alpha=0.3)
    ax_r.spines[["top", "right"]].set_visible(False)
    ax_r.legend(fontsize=9.5, framealpha=0.9)
    plt.tight_layout()
    out = Path(out_dir) / "viz_19_stars_querschnitt.png"
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
    for ax, pct_l, title, n, color in [
        (axes20[0], pct_nat_l, "AI-native",  n_nat_l, COLOR_NATIVE),
        (axes20[1], pct_boo_l, "AI-boosted", n_boo_l, COLOR_BOOSTED),
    ]:
        ax.set_facecolor("white")
        bars = ax.bar(LIC_CATS, pct_l, color=LIC_COLORS, alpha=0.88,
                      edgecolor="white", linewidth=1.5)
        for bar, val in zip(bars, pct_l):
            if val > 1:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.6,
                        f"{val:.1f}%", ha="center", va="bottom",
                        fontsize=10, fontweight="bold")
        ax.set_ylabel("Anteil (%)", fontsize=10)
        ax.set_ylim(0, max(pct_l)*1.18 + 4)
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
    main()
