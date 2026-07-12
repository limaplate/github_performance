"""
explore_repo_package_link.py — Klärt die Beziehung depsProjects ↔ depsPackages

Fragen:
  1. Wie viele Repos in depsProjects werden von mindestens einem Package referenziert?
  2. Wie viele Repos haben KEIN Package das auf sie zeigt?
  3. Wie viele Packages zeigen auf dasselbe Repo? (1:1 vs. n:1)
  4. Wie viele KI-Packages (aus unserer Klassifikation) haben einen Repo-Link?

Ergebnis gibt 100% Klarheit über die Crawl-Struktur.
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
import argparse as _argparse
_p = _argparse.ArgumentParser(add_help=False)
_p.add_argument("--mongo-db", default="upstreamPackages")
_args, _ = _p.parse_known_args()
from common.paths import get_output_dir, get_data_dir

MONGO_URI = get_mongo_uri()
DB_NAME = _args.mongo_db
OUT_JSON = Path(get_output_dir()) / "explore_repo_package_link_results.json"

# KI-Pakete aus letztem Run (für Frage 4)
RESULTS_JSON = Path(get_output_dir()) / "count_signals_results.json"


def ts():
    return datetime.now().strftime("%H:%M:%S")


def main():
    print(f"[{ts()}] Verbinde mit MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]
    db.command("ping")
    print(f"[{ts()}] Verbunden.\n")

    packages = db["depsPackages"]
    projects = db["depsProjects"]

    results = {}

    # ── Grundzahlen ───────────────────────────────────────────────────────────
    print(f"[{ts()}] Block 1: Grundzahlen...")

    n_packages = packages.count_documents({"_id.system": "PYPI"})
    n_projects = projects.count_documents({})
    n_projects_github = projects.count_documents({"type": "GITHUB"})

    print(f"  PyPI-Packages gesamt:     {n_packages:>10,}")
    print(f"  Projekte gesamt:          {n_projects:>10,}")
    print(f"  davon GitHub:             {n_projects_github:>10,}")
    results["n_packages"] = n_packages
    results["n_projects_total"] = n_projects
    results["n_projects_github"] = n_projects_github

    # ── Frage 1: Wie viele Packages haben überhaupt einen Repo-Link? ──────────
    print(f"\n[{ts()}] Block 2: Packages mit Repo-Link...")

    n_with_link = packages.count_documents({
        "_id.system": "PYPI",
        "packageInformation.projects": {"$exists": True, "$not": {"$size": 0}}
    })
    n_without_link = n_packages - n_with_link

    print(f"  Packages MIT Repo-Link:   {n_with_link:>10,}  ({100*n_with_link/n_packages:.1f}%)")
    print(f"  Packages OHNE Repo-Link:  {n_without_link:>10,}  ({100*n_without_link/n_packages:.1f}%)")
    results["n_packages_with_repo_link"] = n_with_link
    results["n_packages_without_repo_link"] = n_without_link

    # ── Frage 2: Alle Repo-Namen die via Packages referenziert werden ─────────
    print(f"\n[{ts()}] Block 3: Distinct Repo-Namen aus packageInformation.projects[]...")
    print(f"  (kann etwas dauern — full collection scan)")

    t0 = time.time()
    linked_repo_names = packages.distinct(
        "packageInformation.projects.name",
        {"_id.system": "PYPI"}
    )
    n_linked_repos = len(linked_repo_names)
    print(f"  Distinct Repo-Namen aus Packages: {n_linked_repos:>8,}  ({time.time()-t0:.1f}s)")
    print(f"  Repos in depsProjects gesamt:     {n_projects:>8,}")
    print(f"  Differenz:                        {n_projects - n_linked_repos:>8,}")
    results["n_distinct_repos_from_packages"] = n_linked_repos

    # ── Frage 3: Repos in depsProjects die von KEINEM Package referenziert werden
    print(f"\n[{ts()}] Block 4: Repos OHNE Package-Referenz...")

    t0 = time.time()
    n_repos_not_linked = projects.count_documents({
        "name": {"$nin": linked_repo_names}
    })
    print(f"  Repos ohne Package-Referenz: {n_repos_not_linked:>8,}  ({time.time()-t0:.1f}s)")

    if n_repos_not_linked == 0:
        print(f"  → 100% der Repos kamen via Package-Links (PyPI-first Crawl bestätigt)")
    else:
        print(f"  → {n_repos_not_linked:,} Repos wurden unabhängig von Packages gecrawlt")

    results["n_repos_without_package_link"] = n_repos_not_linked
    results["crawl_is_pypi_first"] = (n_repos_not_linked == 0)

    # Sample der Repos ohne Link (falls vorhanden)
    if n_repos_not_linked > 0:
        sample = list(projects.find(
            {"name": {"$nin": linked_repo_names}},
            {"name": 1, "type": 1, "description": 1}
        ).limit(5))
        print(f"  Beispiele:")
        for r in sample:
            print(f"    {r.get('name')}  [{r.get('type')}]  {r.get('description','')[:60]}")
        results["repos_without_link_sample"] = [
            {"name": r.get("name"), "type": r.get("type")} for r in sample
        ]

    # ── Frage 4: n:1 Verteilung — wie viele Packages pro Repo? ───────────────
    print(f"\n[{ts()}] Block 5: Verteilung Packages pro Repo (Top 20)...")

    t0 = time.time()
    top_repos = list(packages.aggregate([
        {"$match": {
            "_id.system": "PYPI",
            "packageInformation.projects": {"$exists": True, "$not": {"$size": 0}}
        }},
        {"$unwind": "$packageInformation.projects"},
        {"$group": {
            "_id": "$packageInformation.projects.name",
            "n_packages": {"$sum": 1},
            "packages": {"$push": "$_id.name"}
        }},
        {"$sort": {"n_packages": -1}},
        {"$limit": 20}
    ], allowDiskUse=True))
    print(f"  ({time.time()-t0:.1f}s)")

    print(f"\n  Top-20 Repos nach Anzahl verknüpfter Packages:")
    print(f"  {'Repo':<45} {'Packages':>8}  Beispiele")
    print(f"  {'─'*45} {'─'*8}  {'─'*30}")
    for r in top_repos:
        pkgs = ", ".join(r["packages"][:3])
        print(f"  {str(r['_id']):<45} {r['n_packages']:>8,}  {pkgs}")

    results["top_repos_by_package_count"] = [
        {"repo": r["_id"], "n_packages": r["n_packages"],
         "package_examples": r["packages"][:5]}
        for r in top_repos
    ]

    # Verteilung: wie viele Repos haben genau 1, 2, 3+ Packages?
    dist = list(packages.aggregate([
        {"$match": {
            "_id.system": "PYPI",
            "packageInformation.projects": {"$exists": True, "$not": {"$size": 0}}
        }},
        {"$unwind": "$packageInformation.projects"},
        {"$group": {
            "_id": "$packageInformation.projects.name",
            "n_packages": {"$sum": 1}
        }},
        {"$bucket": {
            "groupBy": "$n_packages",
            "boundaries": [1, 2, 3, 5, 10, 50],
            "default": "50+",
            "output": {"count": {"$sum": 1}}
        }}
    ], allowDiskUse=True))

    print(f"\n  Verteilung Packages pro Repo:")
    for d in dist:
        print(f"    {str(d['_id']):>5} Packages: {d['count']:>8,} Repos")
    results["packages_per_repo_distribution"] = [
        {"bucket": str(d["_id"]), "count": d["count"]} for d in dist
    ]

    # ── Frage 5: Wie viele KI-Packages haben einen Repo-Link? ────────────────
    print(f"\n[{ts()}] Block 6: KI-Packages mit Repo-Link...")

    if RESULTS_JSON.exists():
        with open(RESULTS_JSON, encoding="utf-8") as f:
            ki_results = json.load(f)

        # KI-Package-Namen aus Signal B (names_b war in den Ergebnissen nicht gespeichert)
        # Stattdessen: count über is_ai Flag via HIGH_CONF_REGEX — vereinfacht via count
        # Wir nutzen union_a_or_b als Referenz und schauen wie viele davon Repo-Link haben

        # Packages mit Signal A UND Repo-Link
        from count_signals import HIGH_CONF_REGEX
        n_ki_a_with_link = packages.count_documents({
            "_id.system": "PYPI",
            "packageInformation.description": {"$regex": HIGH_CONF_REGEX, "$options": "i"},
            "packageInformation.projects": {"$exists": True, "$not": {"$size": 0}}
        })
        n_ki_a = ki_results.get("signal_a_high_conf", 0)
        print(f"  KI-Packages Signal A gesamt:     {n_ki_a:>8,}")
        print(f"  davon MIT Repo-Link:             {n_ki_a_with_link:>8,}  ({100*n_ki_a_with_link/n_ki_a:.1f}%)")
        print(f"  davon OHNE Repo-Link:            {n_ki_a - n_ki_a_with_link:>8,}")
        results["ki_signal_a_with_repo_link"] = n_ki_a_with_link
        results["ki_signal_a_without_repo_link"] = n_ki_a - n_ki_a_with_link
    else:
        print(f"  (KI-Ergebnisse JSON nicht gefunden — Block übersprungen)")

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  ZUSAMMENFASSUNG")
    print(f"{'='*60}")
    print(f"  Crawl-Struktur: {'PyPI-first (alle Repos via Packages)' if results.get('crawl_is_pypi_first') else 'GEMISCHT (einige Repos unabhängig gecrawlt)'}")
    print(f"  Packages mit Repo-Link: {n_with_link:,} ({100*n_with_link/n_packages:.1f}%)")
    print(f"  Distinct Repos via Packages: {n_linked_repos:,}")
    print(f"  Repos ohne Package-Referenz: {n_repos_not_linked:,}")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Ergebnisse: {OUT_JSON}")

    client.close()


if __name__ == "__main__":
    main()
