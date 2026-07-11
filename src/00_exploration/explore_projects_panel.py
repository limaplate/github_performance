"""
explore_projects_panel.py — Erkundet depsProjectsPanel

Fragen:
  1. Wie viele Dokumente? Wie viele distinct Projekte?
  2. Welche Felder existieren? Welche sind befuellt?
  3. Welche Zeitspanne? (min/max Snapshot-Datum)
  4. Wie viele Snapshots pro Projekt im Schnitt?
  5. Welche Metriken sind nutzbar? (Stars, Forks, Commits, Contributors, ...)
  6. Wie viel Overlap mit depsProjects (unseren GitHub-Repos)?
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

MONGO_URI = get_mongo_uri()
DB_NAME   = "upstreamPackages"
OUT_JSON  = Path(__file__).parent / "explore_projects_panel_results.json"


def ts():
    return datetime.now().strftime("%H:%M:%S")


def main():
    print(f"[{ts()}] Verbinde mit MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]
    db.command("ping")
    print(f"[{ts()}] Verbunden.\n")

    panel    = db["depsProjectsPanel"]
    projects = db["depsProjects"]
    results  = {}

    # ── Block 1: Grundzahlen ─────────────────────────────────────────────────
    print(f"[{ts()}] Block 1: Grundzahlen...")

    n_total = panel.count_documents({})
    print(f"  Panel-Eintraege gesamt:    {n_total:>10,}")
    results["n_total"] = n_total

    t0 = time.time()
    n_distinct = len(panel.distinct("project.name"))
    print(f"  Distinct Projekte:         {n_distinct:>10,}  ({time.time()-t0:.1f}s)")
    results["n_distinct_projects"] = n_distinct

    n_projects_total = projects.count_documents({})
    print(f"  Projekte in depsProjects:  {n_projects_total:>10,}")
    print(f"  Abdeckung:                 {100*n_distinct/n_projects_total:.1f}%")
    results["n_projects_total"] = n_projects_total
    results["panel_coverage_pct"] = round(100 * n_distinct / n_projects_total, 2)

    # ── Block 2: Beispiel-Dokument — alle Felder sehen ───────────────────────
    print(f"\n[{ts()}] Block 2: Beispiel-Dokument (Feldstruktur)...")

    sample = panel.find_one({})
    if sample:
        def print_fields(d, prefix="", depth=0):
            if depth > 3:
                return
            for k, v in d.items():
                if k == "_id":
                    continue
                if isinstance(v, dict):
                    print(f"  {'  '*depth}{prefix}{k}:  (object)")
                    print_fields(v, "", depth+1)
                elif isinstance(v, list):
                    print(f"  {'  '*depth}{prefix}{k}:  (array, len={len(v)})  "
                          f"Beispiel: {str(v[0])[:60] if v else '[]'}")
                else:
                    print(f"  {'  '*depth}{prefix}{k}:  {type(v).__name__}  =  {str(v)[:80]}")

        print_fields(sample)
        results["sample_fields"] = list(sample.keys())

    # ── Block 3: Zeitspanne ──────────────────────────────────────────────────
    print(f"\n[{ts()}] Block 3: Zeitspanne der Snapshots...")

    # Versuche gaengige Datums-Felder
    for date_field in ["date", "createdAt", "timestamp", "month", "snapshotDate", "period"]:
        sample_with_date = panel.find_one({date_field: {"$exists": True}})
        if sample_with_date:
            print(f"  Datums-Feld gefunden: '{date_field}'  "
                  f"Typ: {type(sample_with_date[date_field]).__name__}  "
                  f"Wert: {sample_with_date[date_field]}")
            results["date_field"] = date_field
            results["date_field_type"] = type(sample_with_date[date_field]).__name__

            # Min/Max
            try:
                min_doc = panel.find_one({date_field: {"$exists": True}},
                                          sort=[(date_field, 1)])
                max_doc = panel.find_one({date_field: {"$exists": True}},
                                          sort=[(date_field, -1)])
                print(f"  Fruehester Snapshot:  {min_doc[date_field]}")
                print(f"  Spaetester Snapshot:  {max_doc[date_field]}")
                results["date_min"] = str(min_doc[date_field])
                results["date_max"] = str(max_doc[date_field])
            except Exception as e:
                print(f"  Min/Max Fehler: {e}")
            break
    else:
        print(f"  Kein Standard-Datumsfeld gefunden — pruefe alle Felder des Samples")

    # ── Block 4: Snapshots pro Projekt ──────────────────────────────────────
    print(f"\n[{ts()}] Block 4: Snapshots pro Projekt...")

    if n_distinct > 0:
        avg_snapshots = n_total / n_distinct
        print(f"  Ø Snapshots pro Projekt:  {avg_snapshots:.1f}")
        results["avg_snapshots_per_project"] = round(avg_snapshots, 1)

    t0 = time.time()
    snapshot_dist = list(panel.aggregate([
        {"$group": {"_id": "$project.name", "n": {"$sum": 1}}},
        {"$bucket": {
            "groupBy": "$n",
            "boundaries": [1, 2, 6, 12, 24, 36, 60],
            "default": "60+",
            "output": {"count": {"$sum": 1}}
        }}
    ], allowDiskUse=True))
    print(f"  ({time.time()-t0:.1f}s)")
    print(f"\n  Snapshots pro Projekt:")
    for d in snapshot_dist:
        print(f"    {str(d['_id']):>5}: {d['count']:>8,} Projekte")
    results["snapshots_per_project_dist"] = [
        {"bucket": str(d["_id"]), "count": d["count"]} for d in snapshot_dist
    ]

    # ── Block 5: Welche Metriken sind befuellt? ──────────────────────────────
    print(f"\n[{ts()}] Block 5: Metriken-Befuellung...")

    # Typische Felder in GitHub-Panel-Daten
    candidate_fields = [
        "stars", "stargazers", "stargazersCount", "starCount",
        "forks", "forksCount", "forkCount",
        "watchers", "watchersCount",
        "openIssues", "openIssuesCount",
        "commits", "commitCount", "totalCommits",
        "contributors", "contributorsCount",
        "pullRequests", "closedIssues",
        "size", "diskUsage",
        "metrics", "activity",
    ]

    # Auch verschachtelte Felder aus dem Sample pruefen
    if sample:
        def get_all_paths(d, prefix=""):
            paths = []
            for k, v in d.items():
                path = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    paths.extend(get_all_paths(v, path))
                else:
                    paths.append(path)
            return paths
        all_paths = get_all_paths(sample)
        print(f"  Alle Felder im Sample ({len(all_paths)}):")
        for p in all_paths:
            if p != "_id":
                print(f"    {p}")
        results["all_field_paths"] = all_paths

    # Befuellung pruefen
    print(f"\n  Befuellung kandidierter Metriken (n=100 Sample):")
    sample_100 = list(panel.find({}).limit(100))
    for field in candidate_fields:
        parts = field.split(".")
        count = 0
        for doc in sample_100:
            val = doc
            try:
                for p in parts:
                    val = val[p]
                if val is not None:
                    count += 1
            except (KeyError, TypeError):
                pass
        if count > 0:
            print(f"    {field:<30} {count:>3}/100 befuellt")
            results[f"field_{field}_sample_pct"] = count

    # ── Block 6: Beispiel-Zeitreihe fuer ein bekanntes Projekt ──────────────
    print(f"\n[{ts()}] Block 6: Beispiel-Zeitreihe 'huggingface/transformers'...")

    example = list(panel.find(
        {"project.name": "huggingface/transformers"}
    ).sort("date", 1).limit(24))

    if not example:
        # Versuche andere Feld-Namen
        for name_field in ["project.name", "name", "projectName", "repo"]:
            example = list(panel.find(
                {name_field: "huggingface/transformers"}
            ).limit(5))
            if example:
                print(f"  Gefunden unter Feld: '{name_field}'")
                break

    if example:
        print(f"  {len(example)} Snapshots gefunden")
        print(f"  Erster: {example[0]}")
    else:
        # Zeige einfach die ersten 3 Dokumente irgendwelcher Projekte
        print(f"  'huggingface/transformers' nicht gefunden — zeige 3 beliebige Eintraege:")
        for doc in panel.find({}).limit(3):
            print(f"  {json.dumps({k: str(v)[:60] for k, v in doc.items() if k != '_id'}, ensure_ascii=False)}")

    # ── Speichern ────────────────────────────────────────────────────────────
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Ergebnisse: {OUT_JSON}")

    client.close()
    print(f"\n[{ts()}] Fertig.")


if __name__ == "__main__":
    main()
