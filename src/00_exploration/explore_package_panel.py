"""
explore_package_panel.py — Erkundet depsPackagePanel

Struktur (bekannt):
  _id: {name, system, date}   — monatlicher Snapshot pro PyPI-Package
  dependentCount               — Pakete die dieses Package als Dep haben
  dependentCountDirect
  dependentCountIndirect
  dependencyCount / Direct / Indirect
  dependents[]                 — Array mit Einzeleintraegen
  dependencies[]
  project: {                   — eingebettete GitHub-Daten (falls vorhanden)
    _id: {nameWithOwner, date}
    commits, contributors, commitsAdditions, commitsDeletions
    authorHHI, committerHHI, authors, committers
  }

Fragen:
  1. Grundzahlen: Eintraege, distinct Packages, Zeitspanne
  2. Wie viele haben ein project-Objekt (GitHub-Link)?
  3. Snapshot-Rhythmus: monatlich? welche Daten?
  4. Befuellung der Kern-Metriken
  5. Overlap mit unseren 37.970 KI-Packages
  6. Beispiel-Zeitreihe: torch, transformers, langchain
"""

import json
import time
from datetime import datetime
from pathlib import Path
from pymongo import MongoClient

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.db_config import get_mongo_uri
from common.compat_v2 import get_panel_collection
import argparse as _argparse
_p = _argparse.ArgumentParser(add_help=False)
_p.add_argument("--mongo-db", default="upstreamPackages")
_args, _ = _p.parse_known_args()
from common.paths import get_output_dir

MONGO_URI = get_mongo_uri()
DB_NAME  = _args.mongo_db
OUT_JSON = Path(get_output_dir()) / "explore_package_panel_results.json"


def ts():
    return datetime.now().strftime("%H:%M:%S")


def main():
    print(f"[{ts()}] Verbinde mit MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]
    db.command("ping")
    print(f"[{ts()}] Verbunden.\n")

    panel   = get_panel_collection(db)
    results = {}

    # ── Block 1: Grundzahlen ─────────────────────────────────────────────────
    print(f"[{ts()}] Block 1: Grundzahlen...")

    # Erstmal ohne Filter — Struktur pruefen
    n_total_all = panel.count_documents({})
    print(f"  Eintraege gesamt (alle):   {n_total_all:>10,}")

    sample = panel.find_one({})
    if sample:
        print(f"  _id Struktur: {sample.get('_id')}")
        print(f"  Felder: {list(sample.keys())}")

    # Versuche verschiedene Filter
    for sys_filter in [
        {"_id.system": "PYPI"},
        {"system": "PYPI"},
        {},
    ]:
        n = panel.count_documents(sys_filter)
        print(f"  Filter {sys_filter}: {n:>10,}")
        if n > 0:
            n_total = n
            base_filter = sys_filter
            break
    else:
        n_total = n_total_all
        base_filter = {}

    results["n_total"] = n_total

    t0 = time.time()
    n_distinct = len(panel.distinct("_id.name", base_filter)) if base_filter != {} else len(panel.distinct("_id.name"))
    if n_distinct == 0:
        # _id hat keinen name-Subfield — andere Struktur
        n_distinct = len(panel.distinct("name", base_filter))
    print(f"  Distinct Packages:         {n_distinct:>10,}  ({time.time()-t0:.1f}s)")
    results["n_distinct_packages"] = n_distinct
    if n_distinct > 0:
        print(f"  Ø Snapshots/Package:       {n_total/n_distinct:.1f}")
        results["avg_snapshots"] = round(n_total / n_distinct, 1)

    # ── Block 2: Zeitspanne + Snapshot-Rhythmus ──────────────────────────────
    print(f"\n[{ts()}] Block 2: Zeitspanne + Rhythmus...")

    min_doc = panel.find_one({}, sort=[("_id.date", 1)])
    max_doc = panel.find_one({}, sort=[("_id.date", -1)])
    print(f"  Fruehester Snapshot: {min_doc['_id']['date']}")
    print(f"  Spaetester Snapshot: {max_doc['_id']['date']}")
    results["date_min"] = str(min_doc["_id"]["date"])
    results["date_max"] = str(max_doc["_id"]["date"])

    t0 = time.time()
    dates = sorted(str(d) for d in panel.distinct("_id.date"))
    print(f"  Distinct Daten: {len(dates)}")
    print(f"  Erste 6:  {dates[:6]}")
    print(f"  Letzte 6: {dates[-6:]}")
    results["n_distinct_dates"] = len(dates)
    results["dates_first6"] = dates[:6]
    results["dates_last6"]  = dates[-6:]

    # ── Block 3: Befuellung Kern-Metriken ────────────────────────────────────
    print(f"\n[{ts()}] Block 3: Befuellung der Kern-Metriken (n=500 Sample)...")

    sample_500 = list(panel.find({}).limit(500))
    metrics = [
        "dependentCount", "dependentCountDirect", "dependentCountIndirect",
        "dependencyCount", "dependencyCountDirect",
        "project",
        "project.commits", "project.contributors",
        "project.commitsAdditions", "project.commitsDeletions",
        "project.authorHHI", "project.authors",
    ]
    print(f"  {'Feld':<35} {'Befuellt':>10}  {'Ø Wert (num)'}")
    print(f"  {'─'*35} {'─'*10}  {'─'*15}")
    for field in metrics:
        parts = field.split(".")
        count = 0
        vals  = []
        for doc in sample_500:
            val = doc
            try:
                for p in parts:
                    val = val[p]
                if val is not None:
                    count += 1
                    if isinstance(val, (int, float)):
                        vals.append(val)
            except (KeyError, TypeError):
                pass
        avg = f"{sum(vals)/len(vals):.1f}" if vals else "—"
        print(f"  {field:<35} {count:>6}/500  {avg:>15}")
        results[f"fill_{field.replace('.','_')}"] = count

    # ── Block 4: Wie viele Packages haben project-Objekt? ────────────────────
    print(f"\n[{ts()}] Block 4: Packages mit GitHub-Projekt-Daten...")

    t0 = time.time()
    n_with_project = panel.count_documents({
        "project": {"$exists": True, "$ne": None}
    })
    pct = 100 * n_with_project / n_total
    print(f"  Snapshots mit project:     {n_with_project:>10,}  ({pct:.1f}%)  ({time.time()-t0:.1f}s)")
    results["n_with_project"] = n_with_project
    results["pct_with_project"] = round(pct, 2)

    # Distinct Packages die irgendwann ein project hatten
    t0 = time.time()
    n_pkgs_with_project = len(panel.distinct("_id.name", {
        "project": {"$exists": True, "$ne": None}
    }))
    print(f"  Distinct Packages:         {n_pkgs_with_project:>10,}  ({time.time()-t0:.1f}s)")
    results["n_distinct_pkgs_with_project"] = n_pkgs_with_project

    # ── Block 5: Overlap mit KI-Packages ─────────────────────────────────────
    print(f"\n[{ts()}] Block 5: Overlap mit KI-Repo-Mapping...")

    KI_MAPPING = Path(get_output_dir()) / "ki_repo_mapping.json"
    if KI_MAPPING.exists():
        with open(KI_MAPPING, encoding="utf-8") as f:
            ki_data = json.load(f)

        ki_repos    = ki_data.get("repo_mapping", {})
        ki_pkg_names = []

        # Sammle Package-Namen aus dem Mapping
        for repo, info in ki_repos.items():
            # Wir brauchen eigentlich Package-Namen, nicht Repo-Namen
            pass

        # Direkt: wie viele der ~37970 KI-Packages haben Panel-Daten?
        # Nutze Signal-B KI-Libraries als Proxy fuer bekannte KI-Packages
        sample_ki_pkgs = [
            "torch", "tensorflow", "transformers", "langchain", "openai",
            "scikit-learn", "keras", "xgboost", "diffusers", "llama-index-core",
            "sentence-transformers", "huggingface-hub", "wandb", "mlflow",
            "lightgbm", "catboost", "pytorch-lightning", "accelerate",
        ]
        print(f"\n  Panel-Daten fuer bekannte KI-Packages:")
        print(f"  {'Package':<30} {'Snapshots':>10} {'Datum-Range'}")
        print(f"  {'─'*30} {'─'*10} {'─'*20}")
        for pkg in sample_ki_pkgs:
            n_snaps = panel.count_documents({"_id.name": pkg, "_id.system": "PYPI"})
            if n_snaps > 0:
                first = panel.find_one({"_id.name": pkg, "_id.system": "PYPI"},
                                        sort=[("_id.date", 1)])
                last  = panel.find_one({"_id.name": pkg, "_id.system": "PYPI"},
                                        sort=[("_id.date", -1)])
                date_range = f"{str(first['_id']['date'])[:7]} – {str(last['_id']['date'])[:7]}"
                print(f"  {pkg:<30} {n_snaps:>10,} {date_range}")
            else:
                print(f"  {pkg:<30} {'—':>10}")
        results["ki_packages_panel_check"] = sample_ki_pkgs
    else:
        print(f"  ki_repo_mapping.json nicht gefunden")

    # ── Block 6: Beispiel-Zeitreihe ─────────────────────────────────────────
    print(f"\n[{ts()}] Block 6: Beispiel-Zeitreihe 'torch'...")

    example = list(panel.find(
        {"_id.name": "torch"}
    ).sort("_id.date", 1))

    if example:
        print(f"  {len(example)} Snapshots")
        print(f"  {'Datum':<12} {'dependents':>12} {'commits':>8} {'contributors':>14} {'additions':>10}")
        print(f"  {'─'*12} {'─'*12} {'─'*8} {'─'*14} {'─'*10}")
        for doc in example:
            proj = doc.get("project") or {}
            print(f"  {str(doc['_id']['date'])[:10]:<12} "
                  f"{doc.get('dependentCount', '—'):>12} "
                  f"{proj.get('commits', '—'):>8} "
                  f"{proj.get('contributors', '—'):>14} "
                  f"{proj.get('commitsAdditions', '—'):>10}")
        results["torch_n_snapshots"] = len(example)
    else:
        print(f"  'torch' nicht im Panel")

    # ── Speichern ────────────────────────────────────────────────────────────
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Ergebnisse: {OUT_JSON}")
    client.close()
    print(f"\n[{ts()}] Fertig.")


if __name__ == "__main__":
    main()
