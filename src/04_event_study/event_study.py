"""
event_study.py — Event Study: Aktivitaet rund um KI-Adoption

Design:
  AI-boosted: t=0 = Monat der ersten KI-Dependency
              t=-24..+24 = 24 Monate vorher / nachher
              Metrik: Commits und Contributors relativ zu t=-1 (= 100%)

  AI-native:  t=0 = erster Panel-Snapshot (Gruendungsmonat)
              t=0..+48 = Wachstumskurve ab Geburt
              Gleiche Metriken als Vergleichsgruppe

Outputs:
  event_study_results.json
  viz_15_event_study_commits.png
  viz_16_event_study_contributors.png
  viz_17_event_study_combined.png
"""

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from pymongo import MongoClient
import statistics

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.db_config import get_mongo_uri
from common.paths import get_output_dir as _get_output_dir
from tqdm import tqdm

import argparse as _argparse
_p = _argparse.ArgumentParser(add_help=False)
_args, _ = _p.parse_known_args()

MONGO_URI = get_mongo_uri()
DB_NAME = "upstreamPackagesV2"
_OUT_DIR = Path(_get_output_dir())
OUT_JSON  = _OUT_DIR / "event_study_results.json"
KI_MAPPING_PATH = _OUT_DIR / "ki_repo_mapping.json"
if not KI_MAPPING_PATH.exists():
    raise FileNotFoundError(f"ki_repo_mapping.json nicht gefunden in {KI_MAPPING_PATH}")

AI_LIBS = {
    "scikit-learn", "torch", "tensorflow", "torchvision", "nltk",
    "spacy", "keras", "torchaudio", "mxnet", "theano",
    "paddlepaddle", "tflearn", "dm-sonnet", "tensorflow-gpu", "tensorflow-cpu",
    "transformers", "openai", "langchain", "datasets", "sentence-transformers",
    "huggingface-hub", "accelerate", "llama-index-core", "peft", "diffusers",
    "tokenizers", "trl", "langchain-core", "langchain-community",
    "llama-index", "llama-cpp-python", "haystack-ai", "litellm",
    "guidance", "dspy", "crewai", "pyautogen", "autogen",
    "autogen-agentchat", "smolagents", "pydantic-ai", "instructor",
    "anthropic", "google-generativeai", "mistralai", "cohere",
    "xgboost", "jax", "gensim", "pytorch-lightning", "wandb",
    "lightgbm", "catboost", "chromadb", "faiss-cpu", "flax",
    "mlflow", "optuna", "qdrant-client", "deepspeed", "timm",
    "bitsandbytes", "stable-baselines3", "pymilvus", "weaviate-client",
    "pinecone", "fastai", "torch-geometric", "imbalanced-learn",
    "unsloth", "bentoml", "evidently",
}


def ts():
    return datetime.now().strftime("%H:%M:%S")

def median(lst):
    return statistics.median(lst) if lst else None

def percentile(lst, p):
    if not lst:
        return None
    s = sorted(lst)
    idx = max(0, min(int(len(s) * p / 100), len(s) - 1))
    return s[idx]

def date_to_ym(dt):
    """Konvertiert datetime zu (year, month) Tupel."""
    if isinstance(dt, datetime):
        return (dt.year, dt.month)
    if isinstance(dt, (int, float)):
        return date_to_ym(datetime.utcfromtimestamp(dt))
    return None

def ym_diff(ym1, ym2):
    """Monatsdifferenz: ym1 - ym2."""
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
    db     = client[DB_NAME]
    db.command("ping")
    print(f"[{ts()}] Verbunden.\n")

    from common.compat_v2 import get_panel_collection
    panel_col    = get_panel_collection(db)
    pkg_col      = db["depsPackages"]
    # Block 1 braucht raw depsVersions (kein Wrapper-Overhead, filter auf _id.name)
    deps_raw_col = db["depsVersions"]

    results = {}

    # ── Block 1: Exakten KI-Adoptions-Monat fuer AI-boosted Repos bestimmen ──
    print(f"[{ts()}] Block 1: KI-Adoptions-Monat fuer AI-boosted Repos...")

    # Repo -> Package-Namen mapping (aus depsPackages)
    t0 = time.time()
    repo_to_pkgs = defaultdict(list)
    docs = list(pkg_col.find(
        {
            "_id.system": "PYPI",
            "packageInformation.projects.name": {"$in": list(boosted_repos)}
        },
        {"_id": 1, "packageInformation.projects": 1}
    ))
    for doc in docs:
        pkg_name = doc["_id"]["name"]
        for proj in doc.get("packageInformation", {}).get("projects", []):
            repo = proj.get("name")
            if repo in boosted_repos:
                repo_to_pkgs[repo].append(pkg_name)
    print(f"  {len(repo_to_pkgs):,} Repos haben Package-Links  ({time.time()-t0:.1f}s)")

    # Fuer jedes Repo: frueheste KI-Dep-Version -> Monat
    t0 = time.time()
    boosted_event_months = {}  # repo -> (year, month)

    all_boosted_pkgs = list({p for pkgs in repo_to_pkgs.values() for p in pkgs})
    print(f"  Lade Versions-Daten fuer {len(all_boosted_pkgs):,} Packages...")

    # Aggregation direkt auf depsVersions (V2-Schema, kein Wrapper)
    # V2: upstreampublishedat (ISO-String), dependencyInformation.dependencies[].package.name + .distance
    ki_first_ts = list(deps_raw_col.aggregate([
        {"$match": {
            "_id.name": {"$in": all_boosted_pkgs},
            "dependenciesprocessed": True,
            "dependencyerror": {"$ne": True},
            "upstreampublishedat": {"$exists": True, "$ne": None},
            "dependencyInformation.dependencies": {"$elemMatch": {
                "package.name": {"$in": list(AI_LIBS)},
                "distance": 1
            }}
        }},
        {"$addFields": {"_pub_ts": {"$toLong": {"$divide": [
            {"$toLong": {"$toDate": "$upstreampublishedat"}}, 1000
        ]}}}},
        {"$sort": {"_pub_ts": 1}},
        {"$group": {
            "_id": "$_id.name",
            "first_ki_ts": {"$first": "$_pub_ts"}
        }}
    ], allowDiskUse=True))

    # Erste Version overall (nicht nur KI-Versionen)
    first_ts_all = list(deps_raw_col.aggregate([
        {"$match": {
            "_id.name": {"$in": all_boosted_pkgs},
            "dependenciesprocessed": True,
            "upstreampublishedat": {"$exists": True, "$ne": None}
        }},
        {"$addFields": {"_pub_ts": {"$toLong": {"$divide": [
            {"$toLong": {"$toDate": "$upstreampublishedat"}}, 1000
        ]}}}},
        {"$sort": {"_pub_ts": 1}},
        {"$group": {"_id": "$_id.name", "first_ts": {"$first": "$_pub_ts"}}}
    ], allowDiskUse=True))
    first_ts_map = {d["_id"]: d["first_ts"] for d in first_ts_all}

    ki_ts_map = {d["_id"]: d["first_ki_ts"] for d in ki_first_ts}
    print(f"  KI-Timestamps fuer {len(ki_ts_map):,} Packages  ({time.time()-t0:.1f}s)")

    # Repo-Level: nimm fruehesten KI-Timestamp ueber alle Packages des Repos
    for repo, pkgs in repo_to_pkgs.items():
        ki_timestamps = [ki_ts_map[p] for p in pkgs if p in ki_ts_map]
        if ki_timestamps:
            earliest_ki_ts = min(ki_timestamps)
            boosted_event_months[repo] = date_to_ym(earliest_ki_ts)

    print(f"  {len(boosted_event_months):,} Repos mit bekanntem KI-Adoptions-Monat")
    results["n_boosted_with_event_month"] = len(boosted_event_months)

    # ── Block 2: Panel-Daten laden und auf t-Achse normieren ─────────────────
    print(f"\n[{ts()}] Block 2: Panel-Daten laden und Event-Fenster berechnen...")

    WINDOW = 24  # Monate vor/nach dem Event

    def build_event_curves(repo_event_map, label, window=WINDOW, ref_t=-1):
        """
        Per-Repo-Normierung: Jedes Repo wird an seinem eigenen ref_t normiert,
        dann werden die Ratios gepoolt. Verhindert Composition Bias.
        ref_t=-1 fuer boosted (ein Monat vor Adoption), ref_t=0 fuer native (Gruendung).
        """
        print(f"  Lade Panel-Daten fuer {label} ({len(repo_event_map):,} Repos, ref_t={ref_t})...")
        t0_time = time.time()

        repo_list = list(repo_event_map.keys())
        BATCH = 500
        # t -> Liste von per-Repo-Ratios
        commits_by_t      = defaultdict(list)
        contributors_by_t = defaultdict(list)
        n_repos_used = 0

        for i in tqdm(range(0, len(repo_list), BATCH), desc=f"event {label}", unit="batch"):
            batch = repo_list[i:i+BATCH]
            docs = list(panel_col.find(
                {
                    "_id.nameWithOwner": {"$in": batch},
                    "_id.date": {"$gte": datetime(2013, 1, 1)}
                },
                {"_id": 1, "commits": 1, "contributors": 1}
            ))

            # Gruppiere nach Repo
            repo_snapshots = defaultdict(list)
            for doc in docs:
                repo = doc["_id"]["nameWithOwner"]
                date = doc["_id"]["date"]
                ym   = date_to_ym(date)
                if ym:
                    repo_snapshots[repo].append({
                        "ym": ym,
                        "commits":      doc.get("commits"),
                        "contributors": doc.get("contributors"),
                    })

            for repo in batch:
                event_ym = repo_event_map.get(repo)
                if not event_ym:
                    continue
                snaps = sorted(repo_snapshots.get(repo, []), key=lambda x: x["ym"])
                if len(snaps) < 3:
                    continue

                # Baue t-indiziertes Dict fuer dieses Repo
                snap_by_t = {}
                for snap in snaps:
                    t = ym_diff(snap["ym"], event_ym)
                    if -window <= t <= window:
                        snap_by_t[t] = snap

                # Referenzwert des Repos bei ref_t
                ref_snap = snap_by_t.get(ref_t)
                if ref_snap is None:
                    # Suche naechstgelegenen Snapshot zu ref_t
                    nearby = sorted(
                        (abs(t - ref_t), t) for t in snap_by_t
                        if abs(t - ref_t) <= 2
                    )
                    if nearby:
                        ref_snap = snap_by_t[nearby[0][1]]

                if ref_snap is None:
                    continue

                ref_commits = ref_snap.get("commits")
                ref_contribs = ref_snap.get("contributors")

                # Ueberspringe Repos mit 0-Referenz (unveraenderlich)
                if not ref_commits or ref_commits == 0:
                    continue

                n_repos_used += 1
                for t, snap in snap_by_t.items():
                    if snap["commits"] is not None and ref_commits:
                        commits_by_t[t].append(snap["commits"] / ref_commits)
                    if snap["contributors"] is not None and ref_contribs and ref_contribs > 0:
                        contributors_by_t[t].append(snap["contributors"] / ref_contribs)

        print(f"  {label}: {n_repos_used:,} Repos mit Panel-Daten  ({time.time()-t0_time:.1f}s)")

        return commits_by_t, contributors_by_t, n_repos_used

    # AI-boosted: t=0 = KI-Adoptions-Monat; Referenz = t=-1 (Monat vor Adoption)
    boosted_commits_t, boosted_contrib_t, n_boosted_used = build_event_curves(
        boosted_event_months, "AI-boosted", ref_t=-1
    )

    # AI-native: t=0 = erster Panel-Snapshot
    # Bestimme t=0 fuer native Repos: fruehester Snapshot im Panel
    print(f"\n  Bestimme Gruendungsmonat fuer AI-native Repos...")
    t0_time = time.time()
    native_first_snap = list(panel_col.aggregate([
        {"$match": {"_id.nameWithOwner": {"$in": list(native_repos)}}},
        {"$group": {
            "_id": "$_id.nameWithOwner",
            "first_date": {"$min": "$_id.date"}
        }}
    ], allowDiskUse=True))
    native_event_months = {
        d["_id"]: date_to_ym(d["first_date"])
        for d in native_first_snap
        if d.get("first_date") and date_to_ym(d["first_date"])
        and date_to_ym(d["first_date"])[0] >= 2013
    }
    print(f"  {len(native_event_months):,} native Repos mit Gruendungsmonat  ({time.time()-t0_time:.1f}s)")

    # AI-native: t=0 = Gruendungsmonat; Referenz = t=0 (Gruendung selbst)
    native_commits_t, native_contrib_t, n_native_used = build_event_curves(
        native_event_months, "AI-native", ref_t=0
    )

    # ── Block 3: Kurven aggregieren ──────────────────────────────────────────
    print(f"\n[{ts()}] Block 3: Kurven aggregieren...")

    t_range = list(range(-WINDOW, WINDOW + 1))

    def aggregate_curve(data_by_t, t_range):
        medians = []
        q25s, q75s = [], []
        ns = []
        for t in t_range:
            vals = [v for v in data_by_t.get(t, []) if v is not None and v >= 0]
            medians.append(median(vals))
            q25s.append(percentile(vals, 25))
            q75s.append(percentile(vals, 75))
            ns.append(len(vals))
        return {"median": medians, "q25": q25s, "q75": q75s, "n_per_t": ns}

    curves = {
        "boosted_commits":      aggregate_curve(boosted_commits_t, t_range),
        "boosted_contributors": aggregate_curve(boosted_contrib_t, t_range),
        "native_commits":       aggregate_curve(native_commits_t,  t_range),
        "native_contributors":  aggregate_curve(native_contrib_t,  t_range),
    }

    # Kurven sind bereits per-Repo normiert (Ratios), kein zweiter Normierungsschritt noetig
    curves_norm = curves

    # Ausgabe: Werte bei key Zeitpunkten
    print(f"\n  Event-Study Ergebnis (per-Repo normiert: boosted ref=t-1, native ref=t=0):")
    print(f"  {'t':>5}  {'Boosted Commits':>18}  {'Native Commits':>16}  "
          f"{'Boosted Contrib':>17}  {'Native Contrib':>16}  {'n(boosted)':>10}")
    print(f"  {'─'*5}  {'─'*18}  {'─'*16}  {'─'*17}  {'─'*16}  {'─'*10}")
    for t in [-12, -6, -3, -1, 0, 1, 3, 6, 12, 18, 24]:
        if t not in t_range:
            continue
        idx = t_range.index(t)
        bc = curves_norm["boosted_commits"]["median"][idx]
        nc = curves_norm["native_commits"]["median"][idx]
        bb = curves_norm["boosted_contributors"]["median"][idx]
        nb = curves_norm["native_contributors"]["median"][idx]
        nb_n = curves["boosted_commits"]["n_per_t"][idx]
        marker = " ← KI-Adoption" if t == 0 else ""
        print(f"  {t:>5}  {str(round(bc,2) if bc else '—'):>18}  "
              f"{str(round(nc,2) if nc else '—'):>16}  "
              f"{str(round(bb,2) if bb else '—'):>17}  "
              f"{str(round(nb,2) if nb else '—'):>16}  "
              f"{nb_n:>10,}{marker}")

    results["t_range"]        = t_range
    results["n_boosted_used"] = n_boosted_used
    results["n_native_used"]  = n_native_used
    results["curves"]         = {k: {
        "median": v["median"], "q25": v["q25"], "q75": v["q75"]
    } for k, v in curves_norm.items()}

    # ── Block 4: Plots ────────────────────────────────────────────────────────
    print(f"\n[{ts()}] Block 4: Event-Study Plots...")
    _draw_event_plots(curves_norm, curves, t_range, n_boosted_used, n_native_used,
                      OUT_JSON.parent)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Ergebnisse: {OUT_JSON}")
    client.close()
    print(f"\n[{ts()}] Fertig.")


def _draw_event_plots(curves_norm, curves_raw, t_range, n_boosted, n_native, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.lines as mlines
    import matplotlib as mpl
    mpl.rcParams["font.family"] = "DejaVu Sans"

    COLOR_NATIVE  = "#1E8449"
    COLOR_BOOSTED = "#E67E22"
    COLOR_ANNO    = "#1A1A2E"
    COLOR_EVENT   = "#E74C3C"
    COLOR_REF     = "#AAAAAA"

    xs = t_range

    def safe(lst):
        return [v if v is not None else float("nan") for v in lst]

    def _add_event_line(ax, label="t = 0\nKI-Adoption"):
        ylim = ax.get_ylim()
        ax.axvline(0, color=COLOR_EVENT, linewidth=2, linestyle="-", alpha=0.85, zorder=4)
        ax.text(0.4, ylim[1] - (ylim[1] - ylim[0]) * 0.05,
                label, fontsize=8.5, color=COLOR_EVENT, va="top")
        ax.axhline(1.0, color=COLOR_REF, linewidth=1, linestyle=":", zorder=1)
        ax.axvspan(-24, 0, alpha=0.04, color=COLOR_BOOSTED)
        ax.axvspan(0,  24, alpha=0.04, color=COLOR_NATIVE)
        ax.text(-12, ylim[0] + (ylim[1]-ylim[0])*0.04, "← Vor Adoption",
                ha="center", fontsize=8, color="#888888", style="italic")
        ax.text( 12, ylim[0] + (ylim[1]-ylim[0])*0.04, "Nach Adoption →",
                ha="center", fontsize=8, color="#888888", style="italic")

    # ── viz_15: AI-boosted Commits + Contributors (Fokus-Plot) ───────────────
    fig, axes15 = plt.subplots(1, 2, figsize=(16, 6))
    fig.patch.set_facecolor("white")
    fig.suptitle(
        f"Event Study: Aktivitaet von AI-boosted Repos rund um die KI-Adoption\n"
        f"Normiert auf t=−1 (Monat vor erster KI-Abhaengigkeit) | Median der per-Repo-Ratios | n={n_boosted:,} Repos",
        fontsize=12, fontweight="bold", color=COLOR_ANNO
    )

    for ax, key, ylabel, title in [
        (axes15[0], "boosted_commits",      "Commit-Ratio (t=−1 = 1.0)", "Commits"),
        (axes15[1], "boosted_contributors", "Contributor-Ratio (t=−1 = 1.0)", "Contributors"),
    ]:
        ax.set_facecolor("white")
        c = curves_norm[key]
        ax.fill_between(xs, safe(c["q25"]), safe(c["q75"]),
                        alpha=0.22, color=COLOR_BOOSTED, label="IQR")
        ax.plot(xs, safe(c["median"]), color=COLOR_BOOSTED, linewidth=2.5,
                label=f"Median (n≈{n_boosted:,})", zorder=3)
        ax.set_xticks(range(-24, 25, 3))
        ax.set_xlabel("Monate relativ zu t=0", fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.grid(axis="both", linestyle="--", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        _add_event_line(ax)
        ax.legend(loc="upper left", fontsize=9, framealpha=0.9)

    insight15 = (
        f"Lesehilfe: Jeder Datenpunkt zeigt den Median der Verhaeltnisse (Aktivitaet bei t) / (Aktivitaet bei t=−1) "
        f"ueber alle {n_boosted:,} AI-boosted Repos. Schattierung = IQR (25.–75. Perzentil). "
        f"Werte > 1.0 bedeuten mehr Aktivitaet als im Monat vor der KI-Adoption."
    )
    fig.text(0.5, -0.03, insight15, fontsize=8.5, ha="center", va="bottom",
             color="#444444", style="italic",
             bbox=dict(boxstyle="round,pad=0.4", fc="#F9F9F9", ec="#CCCCCC", lw=0.7))

    plt.tight_layout(rect=[0, 0.07, 1, 0.93])
    out = Path(out_dir) / "viz_15_event_study_commits.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Gespeichert: {out.name}")

    # ── viz_16: AI-native Wachstumskurve ─────────────────────────────────────
    fig, axes16 = plt.subplots(1, 2, figsize=(16, 6))
    fig.patch.set_facecolor("white")
    fig.suptitle(
        f"Wachstumskurve von AI-native Repos ab Gruendungsmonat (t=0)\n"
        f"Normiert auf t=0 = 1.0 | Median der per-Repo-Ratios | n={n_native:,} Repos",
        fontsize=12, fontweight="bold", color=COLOR_ANNO
    )

    for ax, key, ylabel, title in [
        (axes16[0], "native_commits",      "Commit-Ratio (t=0 = 1.0)", "Commits"),
        (axes16[1], "native_contributors", "Contributor-Ratio (t=0 = 1.0)", "Contributors"),
    ]:
        ax.set_facecolor("white")
        c = curves_norm[key]
        # Nur t >= 0 zeigen (vor Gruendung = kein Datenpunkt)
        xs_pos = [t for t in xs if t >= 0]
        idx_pos = [xs.index(t) for t in xs_pos]
        med_pos = [c["median"][i] for i in idx_pos]
        q25_pos = [c["q25"][i]    for i in idx_pos]
        q75_pos = [c["q75"][i]    for i in idx_pos]

        ax.fill_between(xs_pos, safe(q25_pos), safe(q75_pos),
                        alpha=0.22, color=COLOR_NATIVE, label="IQR")
        ax.plot(xs_pos, safe(med_pos), color=COLOR_NATIVE, linewidth=2.5,
                label=f"Median (n≈{n_native:,})", zorder=3)
        ax.axvline(0, color=COLOR_EVENT, linewidth=2, linestyle="-", alpha=0.85, zorder=4)
        ax.axhline(1.0, color=COLOR_REF, linewidth=1, linestyle=":", zorder=1)
        ax.text(0.4, ax.get_ylim()[1] - (ax.get_ylim()[1]-ax.get_ylim()[0])*0.05,
                "t = 0\nGruendung", fontsize=8.5, color=COLOR_EVENT, va="top")
        ax.set_xticks(range(0, 25, 3))
        ax.set_xlabel("Monate seit Gruendung", fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.grid(axis="both", linestyle="--", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="upper left", fontsize=9, framealpha=0.9)

    plt.tight_layout(rect=[0, 0.04, 1, 0.93])
    out = Path(out_dir) / "viz_16_event_study_contributors.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Gespeichert: {out.name}")

    # ── viz_17: 2x2 Vergleich boosted vs. native (getrennte Y-Achsen) ────────
    fig, axes17 = plt.subplots(2, 2, figsize=(16, 11))
    fig.patch.set_facecolor("white")
    fig.suptitle(
        "Event Study: AI-boosted vs. AI-native — Commits und Contributors\n"
        "Oben: AI-boosted (Fenster −24 bis +24 Monate)  |  Unten: AI-native (ab Gruendung)",
        fontsize=13, fontweight="bold", color=COLOR_ANNO
    )

    # Reihe 0: AI-boosted
    for col, (key, ylabel) in enumerate([
        ("boosted_commits",      "Commit-Ratio (t=−1 = 1.0)"),
        ("boosted_contributors", "Contributor-Ratio (t=−1 = 1.0)"),
    ]):
        ax = axes17[0, col]
        ax.set_facecolor("white")
        c = curves_norm[key]
        ax.fill_between(xs, safe(c["q25"]), safe(c["q75"]),
                        alpha=0.22, color=COLOR_BOOSTED)
        ax.plot(xs, safe(c["median"]), color=COLOR_BOOSTED, linewidth=2.5, zorder=3,
                label=f"AI-boosted (n≈{n_boosted:,})")
        ax.set_xticks(range(-24, 25, 6))
        ax.set_xlabel("Monate relativ zur KI-Adoption", fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(axis="both", linestyle="--", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        _add_event_line(ax, "t = 0")
        ax.legend(loc="upper left", fontsize=8.5)

    axes17[0, 0].set_title("Commits — AI-boosted", fontsize=11, fontweight="bold")
    axes17[0, 1].set_title("Contributors — AI-boosted", fontsize=11, fontweight="bold")

    # Reihe 1: AI-native (nur t >= 0)
    for col, (key, ylabel) in enumerate([
        ("native_commits",      "Commit-Ratio (t=0 = 1.0)"),
        ("native_contributors", "Contributor-Ratio (t=0 = 1.0)"),
    ]):
        ax = axes17[1, col]
        ax.set_facecolor("white")
        c = curves_norm[key]
        xs_pos = [t for t in xs if t >= 0]
        idx_pos = [xs.index(t) for t in xs_pos]
        med_pos = [c["median"][i] for i in idx_pos]
        q25_pos = [c["q25"][i]    for i in idx_pos]
        q75_pos = [c["q75"][i]    for i in idx_pos]
        ax.fill_between(xs_pos, safe(q25_pos), safe(q75_pos),
                        alpha=0.22, color=COLOR_NATIVE)
        ax.plot(xs_pos, safe(med_pos), color=COLOR_NATIVE, linewidth=2.5, zorder=3,
                label=f"AI-native (n≈{n_native:,})")
        ax.axvline(0, color=COLOR_EVENT, linewidth=2, linestyle="-", alpha=0.85, zorder=4)
        ax.axhline(1.0, color=COLOR_REF, linewidth=1, linestyle=":", zorder=1)
        ax.set_xticks(range(0, 25, 3))
        ax.set_xlabel("Monate seit Gruendung", fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(axis="both", linestyle="--", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="upper left", fontsize=8.5)

    axes17[1, 0].set_title("Commits — AI-native", fontsize=11, fontweight="bold")
    axes17[1, 1].set_title("Contributors — AI-native", fontsize=11, fontweight="bold")

    plt.tight_layout(rect=[0, 0.01, 1, 0.94])
    out = Path(out_dir) / "viz_17_event_study_combined.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Gespeichert: {out.name}")


if __name__ == "__main__":
    import sys
    if "--plots-only" in sys.argv:
        # Plots aus gespeichertem JSON neu generieren (kein MongoDB-Zugriff)
        with open(OUT_JSON, encoding="utf-8") as f:
            saved = json.load(f)
        t_range = saved["t_range"]
        n_boosted = saved["n_boosted_used"]
        n_native  = saved["n_native_used"]
        # Kurven aus JSON rekonstruieren
        curves_loaded = {}
        for k, v in saved["curves"].items():
            curves_loaded[k] = {
                "median": v["median"],
                "q25":    v["q25"],
                "q75":    v["q75"],
                "n_per_t": [0] * len(t_range),
            }
        print(f"Regeneriere Plots aus {OUT_JSON}...")
        _draw_event_plots(curves_loaded, curves_loaded, t_range, n_boosted, n_native,
                          OUT_JSON.parent)
        print("Fertig.")
    else:
        main()
