"""
core_analysis.py — Kernanalyse: AI-native vs. AI-boosted

Vergleicht zwei Gruppen auf drei Dimensionen:
  1. Commit-Wachstum (depsProjectsPanel)
  2. Contributor-Wachstum (depsProjectsPanel)
  3. Dependent-Wachstum / Adoption (depsPackagesPanel)

Output:
  core_analysis_results.json
  viz_11_commits_growth.png
  viz_12_contributors_growth.png
  viz_13_dependents_growth.png
  viz_14_summary_comparison.png
"""

import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from pymongo import MongoClient
import statistics

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.db_config import get_mongo_uri

MONGO_URI = get_mongo_uri()
DB_NAME  = "upstreamPackages"
OUT_JSON = Path(__file__).parent / "core_analysis_results.json"

# Suche ki_repo_mapping.json
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


def ts():
    return datetime.now().strftime("%H:%M:%S")


def median(lst):
    return statistics.median(lst) if lst else None


def percentile(lst, p):
    if not lst:
        return None
    s = sorted(lst)
    idx = int(len(s) * p / 100)
    return s[min(idx, len(s) - 1)]


# ── Plot-Funktionen ──────────────────────────────────────────────────────────

def draw_growth_plot(native_curve, boosted_curve, dates,
                     ylabel, title, filename, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib as mpl
    mpl.rcParams["font.family"] = "DejaVu Sans"

    COLOR_NATIVE  = "#1E8449"
    COLOR_BOOSTED = "#E67E22"
    COLOR_ANNO    = "#1A1A2E"

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    xs = list(range(len(dates)))

    # IQR-Baender
    if "q25" in native_curve:
        ax.fill_between(xs, native_curve["q25"], native_curve["q75"],
                        alpha=0.15, color=COLOR_NATIVE, label="_nolegend_")
    if "q25" in boosted_curve:
        ax.fill_between(xs, boosted_curve["q25"], boosted_curve["q75"],
                        alpha=0.15, color=COLOR_BOOSTED, label="_nolegend_")

    # Mediankurven
    ax.plot(xs, native_curve["median"], color=COLOR_NATIVE, linewidth=2.5,
            label=f"AI-native (n={native_curve['n']:,})", zorder=3)
    ax.plot(xs, boosted_curve["median"], color=COLOR_BOOSTED, linewidth=2.5,
            linestyle="--", label=f"AI-boosted (n={boosted_curve['n']:,})", zorder=3)

    # x-Achse: nur jedes 12. Label
    tick_positions = [i for i, d in enumerate(dates) if d.endswith("-01-01") or
                      (i % 12 == 0)]
    tick_labels    = [d[:7] for i, d in enumerate(dates) if i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=8)

    # ChatGPT-Linie
    chatgpt_date = "2022-11-01"
    if chatgpt_date in dates:
        xi = dates.index(chatgpt_date)
        ax.axvline(xi, color="#E74C3C", linestyle=":", linewidth=1.5, alpha=0.7)
        ax.text(xi + 0.3, ax.get_ylim()[1] * 0.92, "ChatGPT\nNov. 2022",
                fontsize=7.5, color="#E74C3C", va="top")

    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold", color=COLOR_ANNO, pad=12)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)

    # Legende mit IQR-Erklaerung
    handles = [
        mpatches.Patch(color=COLOR_NATIVE,  alpha=0.85,
                       label=f"AI-native  (n={native_curve['n']:,})  — Median + IQR"),
        mpatches.Patch(color=COLOR_BOOSTED, alpha=0.85,
                       label=f"AI-boosted  (n={boosted_curve['n']:,})  — Median + IQR"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=9.5, framealpha=0.9)

    plt.tight_layout()
    out = Path(out_dir) / filename
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Gespeichert: {filename}")


def draw_summary_plot(stats_native, stats_boosted, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib as mpl
    mpl.rcParams["font.family"] = "DejaVu Sans"

    COLOR_NATIVE  = "#1E8449"
    COLOR_BOOSTED = "#E67E22"
    COLOR_ANNO    = "#1A1A2E"

    metrics = [
        ("Median Commits\n(letzter Snapshot)", "commits_last_median"),
        ("Median Contributors\n(letzter Snapshot)", "contributors_last_median"),
        ("Median Dependents\n(letzter Snapshot)", "dependents_last_median"),
        ("Commit-Wachstum\n(Faktor seit Start)", "commits_growth_factor"),
        ("Dependent-Wachstum\n(Faktor seit Start)", "dependents_growth_factor"),
    ]

    fig, axes = plt.subplots(1, len(metrics), figsize=(16, 6))
    fig.patch.set_facecolor("white")
    fig.suptitle("AI-native vs. AI-boosted — Vergleich zentraler Kennzahlen",
                 fontsize=13, fontweight="bold", color=COLOR_ANNO, y=1.01)

    for ax, (label, key) in zip(axes, metrics):
        ax.set_facecolor("white")
        n_val = stats_native.get(key, 0) or 0
        b_val = stats_boosted.get(key, 0) or 0
        max_val = max(n_val, b_val, 1)

        bars = ax.bar(["AI-native", "AI-boosted"], [n_val, b_val],
                      color=[COLOR_NATIVE, COLOR_BOOSTED], alpha=0.85,
                      width=0.5, zorder=2)

        # Werte auf Balken
        for bar, val in zip(bars, [n_val, b_val]):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max_val * 0.02,
                    f"{val:,.0f}" if val >= 10 else f"{val:.2f}",
                    ha="center", va="bottom", fontsize=9, fontweight="bold",
                    color=COLOR_ANNO)

        # Ratio
        if b_val > 0:
            ratio = n_val / b_val
            ax.text(0.5, 0.95, f"Ratio: {ratio:.2f}x",
                    ha="center", va="top", transform=ax.transAxes,
                    fontsize=8.5, color="#555555",
                    bbox=dict(boxstyle="round,pad=0.2", fc="#F4F6FA",
                              ec="#CCCCCC", lw=0.6))

        ax.set_title(label, fontsize=9, color=COLOR_ANNO, pad=8)
        ax.set_ylim(0, max_val * 1.25)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="x", labelsize=8)
        ax.tick_params(axis="y", labelsize=7)

    plt.tight_layout()
    out = Path(out_dir) / "viz_14_summary_comparison.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Gespeichert: viz_14_summary_comparison.png")


# ── Haupt-Analyse ────────────────────────────────────────────────────────────

def main():
    print(f"[{ts()}] Lade KI-Repo-Mapping...")
    with open(KI_MAPPING_PATH, encoding="utf-8") as f:
        ki_data = json.load(f)

    ki_mapping = ki_data.get("repo_mapping", {})
    native_repos  = {r for r, d in ki_mapping.items() if d.get("ki_type") == "native"}
    boosted_repos = {r for r, d in ki_mapping.items() if d.get("ki_type") == "boosted"}
    print(f"  AI-native Repos:  {len(native_repos):,}")
    print(f"  AI-boosted Repos: {len(boosted_repos):,}")

    print(f"\n[{ts()}] Verbinde mit MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]
    db.command("ping")
    print(f"[{ts()}] Verbunden.\n")

    panel_repos    = db["depsProjectsPanel"]
    panel_packages = db["depsPackagesPanel"]
    results        = {}

    # ── Block 1: Commit- und Contributor-Kurven aus depsProjectsPanel ────────
    print(f"[{ts()}] Block 1: Commit- und Contributor-Kurven...")

    # Alle validen Daten (ab 2015, kein 1970-Muell)
    date_filter = {"$gte": datetime(2015, 1, 1), "$lte": datetime(2024, 6, 30)}

    def fetch_repo_curves(repo_set, label):
        print(f"  Lade {label} ({len(repo_set):,} Repos)...")
        t0 = time.time()

        # Aggregation: pro Datum -> Median-Werte ueber alle Repos der Gruppe
        raw = list(panel_repos.aggregate([
            {"$match": {
                "_id.nameWithOwner": {"$in": list(repo_set)},
                "_id.date": date_filter
            }},
            {"$group": {
                "_id": "$_id.date",
                "commits_list":      {"$push": "$commits"},
                "contributors_list": {"$push": "$contributors"},
                "n": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ], allowDiskUse=True))

        print(f"  {label}: {len(raw)} Datenpunkte  ({time.time()-t0:.1f}s)")
        return raw

    native_raw  = fetch_repo_curves(native_repos,  "AI-native")
    boosted_raw = fetch_repo_curves(boosted_repos, "AI-boosted")

    # Gemeinsame Datums-Achse
    all_dates = sorted(set(
        str(d["_id"])[:10] for d in native_raw + boosted_raw
    ))
    print(f"  Gemeinsame Zeitachse: {all_dates[0]} — {all_dates[-1]} ({len(all_dates)} Punkte)")

    def build_curve(raw, n_repos):
        date_map = {str(d["_id"])[:10]: d for d in raw}
        medians_c, medians_co = [], []
        q25_c, q75_c = [], []
        q25_co, q75_co = [], []

        for date in all_dates:
            d = date_map.get(date)
            if d:
                cl  = [v for v in d["commits_list"]      if v is not None]
                col = [v for v in d["contributors_list"] if v is not None]
            else:
                cl = col = []

            medians_c.append(median(cl)  or 0)
            medians_co.append(median(col) or 0)
            q25_c.append(percentile(cl,  25) or 0)
            q75_c.append(percentile(cl,  75) or 0)
            q25_co.append(percentile(col, 25) or 0)
            q75_co.append(percentile(col, 75) or 0)

        return {
            "commits":      {"median": medians_c,  "q25": q25_c,  "q75": q75_c,  "n": n_repos},
            "contributors": {"median": medians_co, "q25": q25_co, "q75": q75_co, "n": n_repos},
        }

    native_curves  = build_curve(native_raw,  len(native_repos))
    boosted_curves = build_curve(boosted_raw, len(boosted_repos))

    results["dates"] = all_dates
    results["native_commits_median"]       = native_curves["commits"]["median"]
    results["boosted_commits_median"]      = boosted_curves["commits"]["median"]
    results["native_contributors_median"]  = native_curves["contributors"]["median"]
    results["boosted_contributors_median"] = boosted_curves["contributors"]["median"]

    # ── Block 2: Dependent-Kurven aus depsPackagesPanel ────────────────────────
    print(f"\n[{ts()}] Block 2: Dependent-Kurven aus depsPackagesPanel...")

    # Direkt in depsPackagesPanel: welche Packages gehoeren zu native/boosted Repos?
    # Weg: project._id.nameWithOwner in repo_set
    # In Batches weil $in mit 4000+ Eintraegen langsam sein kann

    def get_pkg_names_from_panel(repo_set, label):
        print(f"  Suche Panel-Packages fuer {label} ({len(repo_set):,} Repos)...")
        t0 = time.time()
        repo_list = list(repo_set)
        BATCH = 1000
        pkg_names = set()
        for i in range(0, len(repo_list), BATCH):
            batch = repo_list[i:i+BATCH]
            names = panel_packages.distinct(
                "_id.name",
                {"project._id.nameWithOwner": {"$in": batch}}
            )
            pkg_names.update(names)
        print(f"  {len(pkg_names):,} Packages mit Panel-Daten  ({time.time()-t0:.1f}s)")
        # Debug: zeige ein paar Beispiele
        sample = list(pkg_names)[:5]
        for name in sample:
            n = panel_packages.count_documents({"_id.name": name})
            print(f"    {name}: {n} Snapshots")
        return pkg_names

    native_pkg_names  = get_pkg_names_from_panel(native_repos,  "AI-native")
    boosted_pkg_names = get_pkg_names_from_panel(boosted_repos, "AI-boosted")

    def fetch_dependent_curves(pkg_names, label):
        if not pkg_names:
            print(f"  {label}: keine Packages gefunden — uebersprungen")
            return []
        print(f"  Lade Dependents {label} ({len(pkg_names):,} Packages)...")
        t0 = time.time()
        date_agg = defaultdict(list)
        date_agg_nonzero = defaultdict(list)
        BATCH = 500
        pkg_list = list(pkg_names)
        for i in range(0, len(pkg_list), BATCH):
            batch = pkg_list[i:i+BATCH]
            docs = panel_packages.find(
                {
                    "_id.name": {"$in": batch},
                    "_id.date": date_filter
                },
                {"_id": 1, "dependentCount": 1}
            )
            for doc in docs:
                date_key = str(doc["_id"]["date"])[:10]
                val = doc.get("dependentCount")
                if val is not None:
                    date_agg[date_key].append(val)
                    if val > 0:
                        date_agg_nonzero[date_key].append(val)

        total_snaps = sum(len(v) for v in date_agg.values())
        nonzero_snaps = sum(len(v) for v in date_agg_nonzero.values())
        pct_nonzero = 100 * nonzero_snaps / total_snaps if total_snaps > 0 else 0
        print(f"  {label}: {len(date_agg)} Datenpunkte, {total_snaps:,} Snapshots  ({time.time()-t0:.1f}s)")
        print(f"  davon dependentCount > 0: {pct_nonzero:.1f}%")

        # Gibt beide zurueck: alle + nur nonzero
        raw_all = [{"_id": k, "dep_list": v, "dep_nonzero": date_agg_nonzero.get(k, []), "n": len(v)}
                   for k, v in date_agg.items()]
        raw_all.sort(key=lambda x: x["_id"])
        return raw_all

    native_dep_raw  = fetch_dependent_curves(native_pkg_names,  "AI-native")
    boosted_dep_raw = fetch_dependent_curves(boosted_pkg_names, "AI-boosted")

    dep_dates = sorted(set(
        d["_id"][:10] if isinstance(d["_id"], str) else str(d["_id"])[:10]
        for d in native_dep_raw + boosted_dep_raw
    ))

    def build_dep_curve(raw, n_repos):
        date_map = {
            (d["_id"][:10] if isinstance(d["_id"], str) else str(d["_id"])[:10]): d
            for d in raw
        }
        medians, q25s, q75s = [], [], []
        medians_nz, q25s_nz, q75s_nz = [], [], []
        for date in dep_dates:
            d = date_map.get(date)
            vals    = [v for v in d["dep_list"]    if v is not None] if d else []
            vals_nz = [v for v in d.get("dep_nonzero", []) if v is not None] if d else []
            medians.append(median(vals) or 0)
            q25s.append(percentile(vals, 25) or 0)
            q75s.append(percentile(vals, 75) or 0)
            medians_nz.append(median(vals_nz) or 0)
            q25s_nz.append(percentile(vals_nz, 25) or 0)
            q75s_nz.append(percentile(vals_nz, 75) or 0)
        return {
            "median": medians, "q25": q25s, "q75": q75s,
            "median_nz": medians_nz, "q25_nz": q25s_nz, "q75_nz": q75s_nz,
            "n": n_repos
        }

    native_dep_curve  = build_dep_curve(native_dep_raw,  len(native_repos))
    boosted_dep_curve = build_dep_curve(boosted_dep_raw, len(boosted_repos))

    results["dep_dates"]               = dep_dates
    results["native_dep_median"]       = native_dep_curve["median"]
    results["boosted_dep_median"]      = boosted_dep_curve["median"]

    # ── Block 3: Deskriptive Statistiken ─────────────────────────────────────
    print(f"\n[{ts()}] Block 3: Deskriptive Statistiken...")

    def last_nonzero(lst):
        for v in reversed(lst):
            if v and v > 0:
                return v
        return 0

    # Wachstumsfaktor: per-Repo (letzter / erster Snapshot) -> Median ueber alle Repos
    def fetch_per_repo_growth(repo_set, metric_field, label):
        print(f"  Per-Repo Wachstum {label} ({metric_field})...")
        t0 = time.time()
        raw = list(panel_repos.aggregate([
            {"$match": {
                "_id.nameWithOwner": {"$in": list(repo_set)},
                "_id.date": date_filter,
                metric_field: {"$exists": True, "$gt": 0}
            }},
            {"$sort": {"_id.date": 1}},
            {"$group": {
                "_id": "$_id.nameWithOwner",
                "first_val": {"$first": f"${metric_field}"},
                "last_val":  {"$last":  f"${metric_field}"},
                "n_snapshots": {"$sum": 1}
            }},
            {"$match": {"n_snapshots": {"$gte": 3}, "first_val": {"$gt": 0}}},
            {"$addFields": {"growth": {"$divide": ["$last_val", "$first_val"]}}},
            {"$group": {
                "_id": None,
                "growth_list": {"$push": "$growth"},
                "last_list":   {"$push": "$last_val"},
                "n": {"$sum": 1}
            }}
        ], allowDiskUse=True))
        print(f"  ({time.time()-t0:.1f}s)")
        if raw:
            gl = raw[0]["growth_list"]
            ll = raw[0]["last_list"]
            return {
                "growth_median": round(median(gl), 2),
                "last_median":   round(median(ll), 1),
                "n": raw[0]["n"]
            }
        return {"growth_median": None, "last_median": None, "n": 0}

    native_commit_stats  = fetch_per_repo_growth(native_repos,  "commits",      "AI-native")
    boosted_commit_stats = fetch_per_repo_growth(boosted_repos, "commits",      "AI-boosted")
    native_contrib_stats = fetch_per_repo_growth(native_repos,  "contributors", "AI-native")
    boosted_contrib_stats= fetch_per_repo_growth(boosted_repos, "contributors", "AI-boosted")

    # Dependent-Wachstum per-Package
    def fetch_dep_growth(pkg_names, label):
        print(f"  Per-Package Dependent-Wachstum {label}...")
        t0 = time.time()
        raw = list(panel_packages.aggregate([
            {"$match": {
                "_id.name": {"$in": list(pkg_names)},
                "_id.date": date_filter,
                "dependentCount": {"$gt": 0}
            }},
            {"$sort": {"_id.date": 1}},
            {"$group": {
                "_id": "$_id.name",
                "first_val": {"$first": "$dependentCount"},
                "last_val":  {"$last":  "$dependentCount"},
                "n": {"$sum": 1}
            }},
            {"$match": {"n": {"$gte": 3}, "first_val": {"$gt": 0}}},
            {"$addFields": {"growth": {"$divide": ["$last_val", "$first_val"]}}},
            {"$group": {
                "_id": None,
                "growth_list": {"$push": "$growth"},
                "last_list":   {"$push": "$last_val"},
                "n": {"$sum": 1}
            }}
        ], allowDiskUse=True))
        print(f"  ({time.time()-t0:.1f}s)")
        if raw:
            return {
                "growth_median": round(median(raw[0]["growth_list"]), 2),
                "last_median":   round(median(raw[0]["last_list"]), 1),
                "n": raw[0]["n"]
            }
        return {"growth_median": None, "last_median": None, "n": 0}

    native_dep_growth  = fetch_dep_growth(native_pkg_names,  "AI-native")
    boosted_dep_growth = fetch_dep_growth(boosted_pkg_names, "AI-boosted")

    stats_native = {
        "commits_last_median":       native_commit_stats["last_median"],
        "contributors_last_median":  native_contrib_stats["last_median"],
        "dependents_last_median":    last_nonzero(native_dep_curve["median_nz"]),
        "dependents_last_median_nz": native_dep_growth["last_median"],
        "commits_growth_factor":     native_commit_stats["growth_median"],
        "dependents_growth_factor":  native_dep_growth["growth_median"],
    }
    stats_boosted = {
        "commits_last_median":       boosted_commit_stats["last_median"],
        "contributors_last_median":  boosted_contrib_stats["last_median"],
        "dependents_last_median":    last_nonzero(boosted_dep_curve["median_nz"]),
        "dependents_last_median_nz": boosted_dep_growth["last_median"],
        "commits_growth_factor":     boosted_commit_stats["growth_median"],
        "dependents_growth_factor":  boosted_dep_growth["growth_median"],
    }

    print(f"\n  {'Kennzahl':<35} {'AI-native':>12} {'AI-boosted':>12} {'Ratio':>8}")
    print(f"  {'─'*35} {'─'*12} {'─'*12} {'─'*8}")
    for key, label in [
        ("commits_last_median",      "Median Commits (aktuell)"),
        ("contributors_last_median", "Median Contributors (aktuell)"),
        ("dependents_last_median",   "Median Dependents (aktuell)"),
        ("commits_growth_factor",    "Commit-Wachstumsfaktor"),
        ("dependents_growth_factor", "Dependent-Wachstumsfaktor"),
    ]:
        n = stats_native.get(key) or 0
        b = stats_boosted.get(key) or 0
        ratio = f"{n/b:.2f}x" if b and b > 0 else "—"
        print(f"  {label:<35} {n:>12,.1f} {b:>12,.1f} {ratio:>8}")

    results["stats_native"]  = stats_native
    results["stats_boosted"] = stats_boosted

    # ── Block 4: Plots generieren ─────────────────────────────────────────────
    print(f"\n[{ts()}] Block 4: Plots generieren...")

    draw_growth_plot(
        native_curves["commits"], boosted_curves["commits"],
        all_dates,
        ylabel="Median Commits (kumulativ)",
        title="Commit-Aktivitaet: AI-native vs. AI-boosted\nMedian ueber alle Repos | Schattierung = IQR (25-75%)",
        filename="viz_11_commits_growth.png",
        out_dir=OUT_JSON.parent
    )

    draw_growth_plot(
        native_curves["contributors"], boosted_curves["contributors"],
        all_dates,
        ylabel="Median Contributors (kumulativ)",
        title="Contributor-Wachstum: AI-native vs. AI-boosted\nMedian ueber alle Repos | Schattierung = IQR (25-75%)",
        filename="viz_12_contributors_growth.png",
        out_dir=OUT_JSON.parent
    )

    # viz_13: nur Packages mit dependentCount > 0 (sonst Median immer 0)
    native_dep_nz  = {"median": native_dep_curve["median_nz"],
                      "q25": native_dep_curve["q25_nz"],
                      "q75": native_dep_curve["q75_nz"],
                      "n": native_dep_growth["n"]}
    boosted_dep_nz = {"median": boosted_dep_curve["median_nz"],
                      "q25": boosted_dep_curve["q25_nz"],
                      "q75": boosted_dep_curve["q75_nz"],
                      "n": boosted_dep_growth["n"]}
    draw_growth_plot(
        native_dep_nz, boosted_dep_nz,
        dep_dates,
        ylabel="Median dependentCount (nur Packages mit >0 Dependents)",
        title="Package-Adoption (dependentCount): AI-native vs. AI-boosted\nNur Packages mit mind. 1 Dependent | Median | Schattierung = IQR",
        filename="viz_13_dependents_growth.png",
        out_dir=OUT_JSON.parent
    )

    draw_summary_plot(stats_native, stats_boosted, OUT_JSON.parent)

    # ── Speichern ────────────────────────────────────────────────────────────
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Ergebnisse: {OUT_JSON}")

    client.close()
    print(f"\n[{ts()}] Fertig.")


if __name__ == "__main__":
    main()
