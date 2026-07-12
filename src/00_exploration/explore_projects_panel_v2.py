"""
explore_projects_panel_v2.py — Panel mit korrekten Feldnamen

Felder laut erstem Run:
  _id.nameWithOwner  — Repo-Name (owner/repo)
  _id.date           — Snapshot-Datum
  commits, contributors, commitsAdditions, commitsDeletions, commitsTotal
  authors, committers, authorHHI, committerHHI
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
from common.paths import get_output_dir

MONGO_URI = get_mongo_uri()
DB_NAME  = "upstreamPackages"
OUT_JSON = Path(get_output_dir()) / "explore_projects_panel_v2_results.json"


def ts():
    return datetime.now().strftime("%H:%M:%S")


def main():
    print(f"[{ts()}] Verbinde mit MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]
    db.command("ping")
    print(f"[{ts()}] Verbunden.\n")

    panel   = db["depsProjectsPanel"]
    results = {}

    # ── Block 1: Distinct Projekte (richtiges Feld) ──────────────────────────
    print(f"[{ts()}] Block 1: Distinct Projekte...")

    n_total = panel.count_documents({})
    print(f"  Eintraege gesamt: {n_total:>10,}")
    results["n_total"] = n_total

    t0 = time.time()
    n_distinct = len(panel.distinct("_id.nameWithOwner"))
    print(f"  Distinct Repos:   {n_distinct:>10,}  ({time.time()-t0:.1f}s)")
    results["n_distinct_repos"] = n_distinct
    print(f"  Ø Snapshots/Repo: {n_total/n_distinct:.1f}")
    results["avg_snapshots"] = round(n_total / n_distinct, 1)

    # ── Block 2: Zeitspanne ──────────────────────────────────────────────────
    print(f"\n[{ts()}] Block 2: Zeitspanne...")

    min_doc = panel.find_one({}, sort=[("_id.date", 1)])
    max_doc = panel.find_one({}, sort=[("_id.date", -1)])
    print(f"  Fruehester Snapshot: {min_doc['_id']['date']}")
    print(f"  Spaetester Snapshot: {max_doc['_id']['date']}")
    results["date_min"] = str(min_doc["_id"]["date"])
    results["date_max"] = str(max_doc["_id"]["date"])

    # ── Block 3: Snapshots pro Repo Verteilung ───────────────────────────────
    print(f"\n[{ts()}] Block 3: Snapshots pro Repo...")

    t0 = time.time()
    snap_dist = list(panel.aggregate([
        {"$group": {"_id": "$_id.nameWithOwner", "n": {"$sum": 1}}},
        {"$bucket": {
            "groupBy": "$n",
            "boundaries": [1, 2, 6, 12, 24, 36, 60],
            "default": "60+",
            "output": {"count": {"$sum": 1}}
        }}
    ], allowDiskUse=True))
    print(f"  ({time.time()-t0:.1f}s)")
    print(f"\n  Snapshots pro Repo:")
    for d in snap_dist:
        print(f"    {str(d['_id']):>5}: {d['count']:>8,} Repos")
    results["snapshots_dist"] = [{"bucket": str(d["_id"]), "count": d["count"]} for d in snap_dist]

    # ── Block 4: Distinct Datumswerte (Snapshot-Rhythmus) ────────────────────
    print(f"\n[{ts()}] Block 4: Snapshot-Rhythmus...")

    t0 = time.time()
    dates = panel.distinct("_id.date")
    dates_sorted = sorted(str(d) for d in dates)
    print(f"  Anzahl distinct Daten: {len(dates_sorted)}")
    print(f"  Erste 10: {dates_sorted[:10]}")
    print(f"  Letzte 5: {dates_sorted[-5:]}")
    results["n_distinct_dates"] = len(dates_sorted)
    results["dates_sample_first10"] = dates_sorted[:10]
    results["dates_sample_last5"]   = dates_sorted[-5:]

    # ── Block 5: Beispiel-Zeitreihe transformers ─────────────────────────────
    print(f"\n[{ts()}] Block 5: Beispiel 'huggingface/transformers'...")

    example = list(panel.find(
        {"_id.nameWithOwner": "huggingface/transformers"}
    ).sort("_id.date", 1).limit(36))

    if example:
        print(f"  {len(example)} Snapshots gefunden")
        print(f"  {'Datum':<25} {'Commits':>8} {'Contributors':>14} {'Additions':>10} {'Deletions':>10}")
        print(f"  {'─'*25} {'─'*8} {'─'*14} {'─'*10} {'─'*10}")
        for doc in example:
            print(f"  {str(doc['_id']['date']):<25} "
                  f"{doc.get('commits', '—'):>8} "
                  f"{doc.get('contributors', '—'):>14} "
                  f"{doc.get('commitsAdditions', '—'):>10} "
                  f"{doc.get('commitsDeletions', '—'):>10}")
        results["transformers_n_snapshots"] = len(example)
    else:
        print(f"  Nicht gefunden — zeige beliebiges Repo mit mehreren Snapshots:")
        sample_repo = list(panel.aggregate([
            {"$group": {"_id": "$_id.nameWithOwner", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 1}
        ]))[0]
        print(f"  Repo mit meisten Snapshots: {sample_repo['_id']} ({sample_repo['n']} Snapshots)")
        example2 = list(panel.find(
            {"_id.nameWithOwner": sample_repo["_id"]}
        ).sort("_id.date", 1).limit(6))
        for doc in example2:
            print(f"  {str(doc['_id']['date']):<25} commits={doc.get('commits','—')} "
                  f"contributors={doc.get('contributors','—')}")
        results["fallback_example_repo"] = sample_repo["_id"]

    # ── Block 6: Overlap mit KI-Repo-Mapping ────────────────────────────────
    print(f"\n[{ts()}] Block 6: Overlap depsProjectsPanel <-> KI-Repo-Mapping...")

    KI_MAPPING = Path(get_output_dir()) / "ki_repo_mapping.json"
    if KI_MAPPING.exists():
        with open(KI_MAPPING, encoding="utf-8") as f:
            ki_data = json.load(f)
        ki_repos      = set(ki_data.get("repo_mapping", {}).keys())
        ki_repos_list = list(ki_repos)
        print(f"  KI-Repos im Mapping:        {len(ki_repos):>8,}")

        # Distinct KI-Repos die in depsProjectsPanel vorhanden sind
        t0 = time.time()
        panel_ki_repos = panel.distinct(
            "_id.nameWithOwner",
            {"_id.nameWithOwner": {"$in": ki_repos_list}}
        )
        print(f"  Davon in depsProjectsPanel: {len(panel_ki_repos):>8,}  ({time.time()-t0:.1f}s)")
        print(f"  Abdeckung:                  {100*len(panel_ki_repos)/len(ki_repos):.1f}%")

        # Snapshot-Anzahl fuer diese KI-Repos
        t0 = time.time()
        n_ki_snapshots = panel.count_documents(
            {"_id.nameWithOwner": {"$in": panel_ki_repos}}
        )
        print(f"  Snapshots fuer KI-Repos:    {n_ki_snapshots:>8,}  ({time.time()-t0:.1f}s)")
        print(f"  Ø Snapshots/KI-Repo:        {n_ki_snapshots/len(panel_ki_repos):.1f}")

        # Native vs. Boosted Aufschluesslung
        ki_mapping = ki_data.get("repo_mapping", {})
        native_repos  = [r for r in panel_ki_repos if ki_mapping.get(r, {}).get("ki_type") == "native"]
        boosted_repos = [r for r in panel_ki_repos if ki_mapping.get(r, {}).get("ki_type") == "boosted"]
        unknown_repos = [r for r in panel_ki_repos if ki_mapping.get(r, {}).get("ki_type") == "unknown"]
        print(f"\n  Davon AI-native:            {len(native_repos):>8,}")
        print(f"  Davon AI-boosted:           {len(boosted_repos):>8,}")
        print(f"  Davon unknown:              {len(unknown_repos):>8,}")

        results["n_ki_repos_in_mapping"]   = len(ki_repos)
        results["n_ki_repos_with_panel"]   = len(panel_ki_repos)
        results["ki_panel_coverage_pct"]   = round(100 * len(panel_ki_repos) / len(ki_repos), 2)
        results["n_ki_snapshots"]          = n_ki_snapshots
        results["n_native_in_panel"]       = len(native_repos)
        results["n_boosted_in_panel"]      = len(boosted_repos)
        results["n_unknown_in_panel"]      = len(unknown_repos)
    else:
        print(f"  ki_repo_mapping.json nicht gefunden — Block uebersprungen")

    # ── Speichern ────────────────────────────────────────────────────────────
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Ergebnisse: {OUT_JSON}")
    client.close()
    print(f"\n[{ts()}] Fertig.")


if __name__ == "__main__":
    main()
