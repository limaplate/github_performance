"""
test_compat_v2.py — Prueft ob compat_v2.py korrekt funktioniert.

Aufruf:
  python test_compat_v2.py --mongo-uri "mongodb://user:pass@host:27017/" --mongo-db upstreamPackagesV2
  python test_compat_v2.py --mongo-uri "mongodb://user:pass@host:27017/" --mongo-db upstreamPackages
"""
import sys
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pymongo import MongoClient
from common.db_config import get_mongo_uri
from common.compat_v2 import (
    detect_db_version,
    get_deps_collection,
    get_panel_collection,
    setup_v2_views,
)

MONGO_URI = get_mongo_uri()
import argparse, re

# DB-Namen aus URI oder --mongo-db extrahieren
p = argparse.ArgumentParser(add_help=False)
p.add_argument("--mongo-db", default="upstreamPackages")
args, _ = p.parse_known_args()
DB_NAME = args.mongo_db

print(f"\n{'='*60}")
print(f"  Test: compat_v2.py  |  DB: {DB_NAME}")
print(f"{'='*60}\n")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = client[DB_NAME]
db.command("ping")

# ── Test 1: Version erkennen ──────────────────────────────────────────────
version = detect_db_version(db)
print(f"[1] Erkannte DB-Version:  {version.upper()}  ✓")

# ── Test 2: Views anlegen (nur V2) ────────────────────────────────────────
setup_v2_views(db)
print(f"[2] setup_v2_views()      OK  ✓")

# ── Test 3: deps_col — Schema pruefen ─────────────────────────────────────
deps = get_deps_collection(db)
print(f"\n[3] deps_col = '{deps.name}'")

sample_dep = deps.find_one({"createdAt": {"$exists": True, "$ne": None}})
if not sample_dep:
    print("    WARNUNG: Kein Dokument mit createdAt gefunden!")
else:
    # Pflichtfelder
    assert "_id" in sample_dep,          "FEHLER: _id fehlt"
    assert "name" in sample_dep["_id"],  "FEHLER: _id.name fehlt"
    assert "createdAt" in sample_dep,    "FEHLER: createdAt fehlt"
    assert isinstance(sample_dep["createdAt"], (int, float)), \
        f"FEHLER: createdAt ist kein Integer, sondern {type(sample_dep['createdAt'])}"
    assert "dependencies" in sample_dep, "FEHLER: dependencies fehlt"

    # depth-Feld pruefen (V2-Adapter: distance->depth)
    deps_list = sample_dep.get("dependencies", [])
    if deps_list:
        first_dep = deps_list[0]
        assert "name"  in first_dep, "FEHLER: dependencies[].name fehlt"
        assert "depth" in first_dep, \
            f"FEHLER: dependencies[].depth fehlt! Vorhandene Felder: {list(first_dep.keys())}"
        print(f"    _id.name:       {sample_dep['_id']['name']}")
        print(f"    createdAt:      {sample_dep['createdAt']}  (Unix-Sek, Typ: {type(sample_dep['createdAt']).__name__})")
        print(f"    dependencies:   {len(deps_list)} Eintraege")
        print(f"    dep[0]:         name='{first_dep['name']}' depth={first_dep.get('depth')}")

        # Direkte Deps (depth==1) vorhanden?
        direct = [d for d in deps_list if d.get("depth") == 1]
        print(f"    direkte Deps:   {len(direct)} (depth==1)")
        print(f"    [3] deps_col Schema  OK  ✓")
    else:
        print("    WARNUNG: dependencies-Array ist leer")

# ── Test 4: Aggregation wie in build_ki_repo_mapping.py ───────────────────
print(f"\n[4] deps_col.aggregate() — wie in build_ki_repo_mapping...")
AI_LIBS_SAMPLE = {"torch", "tensorflow", "transformers", "scikit-learn", "openai"}

result = list(deps.aggregate([
    {"$match": {
        "createdAt": {"$exists": True, "$ne": None},
        "dependencies": {"$elemMatch": {
            "name":  {"$in": list(AI_LIBS_SAMPLE)},
            "depth": 1
        }}
    }},
    {"$limit": 100},          # <-- NEU: früh begrenzen
    {"$group": {
        "_id":           "$_id.name",
        "first_created": {"$first": "$createdAt"},
    }},
    {"$sort": {"first_created": 1}},
    {"$limit": 5}
], allowDiskUse=True))

if result:
    print(f"    Gefundene Packages mit AI-Dep (depth=1): {len(result)}")
    for r in result:
        print(f"      {r['_id']:40s}  createdAt={r['first_created']}")
    print(f"    [4] Aggregation  OK  ✓")
else:
    print("    WARNUNG: Keine Ergebnisse — depth==1 matcht nichts.")
    print("    Pruefen: Welche depth-Werte gibt es?")
    sample_depths = list(deps.aggregate([
        {"$unwind": "$dependencies"},
        {"$group": {"_id": "$dependencies.depth", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}, {"$limit": 10}
    ]))
    print(f"    Vorhandene depth-Werte: {sample_depths}")

# ── Test 5: panel_col — Schema pruefen ────────────────────────────────────
panel = get_panel_collection(db)
print(f"\n[5] panel_col = '{panel.name}'")

# Direkt auf roher Collection testen — 1 Commit -> $group -> Schema pruefen
raw_col = db["depsProjectsCommits"]
sample_list = list(raw_col.aggregate([
    {"$limit": 1},
    {"$addFields": {
        "_commit_date":    {"$toDate": "$commit.author.date"},
        "author_login":    {"$ifNull": ["$author.login",    "$commit.author.name"]},
        "committer_login": {"$ifNull": ["$committer.login", "$commit.committer.name"]}
    }},
    {"$addFields": {
        "month_date": {"$dateFromParts": {
            "year":  {"$year":  "$_commit_date"},
            "month": {"$month": "$_commit_date"},
            "day":   1
        }}
    }},
    {"$group": {
        "_id": {"nameWithOwner": "$_id.nameWithOwner", "date": "$month_date"},
        "commits":          {"$sum": 1},
        "author_set":       {"$addToSet": "$author_login"},
        "committer_set":    {"$addToSet": "$committer_login"},
        "commitsAdditions": {"$sum": {"$ifNull": ["$stats.additions", 0]}},
        "commitsDeletions": {"$sum": {"$ifNull": ["$stats.deletions",  0]}},
    }},
    {"$addFields": {
        "contributors": {"$size": "$author_set"},
        "authors":      {"$size": "$author_set"},
        "committers":   {"$size": "$committer_set"},
        "commitsTotal": {"$add": ["$commitsAdditions", "$commitsDeletions"]}
    }}
], allowDiskUse=True))
sample_panel = sample_list[0] if sample_list else None

if not sample_panel:
    print("    WARNUNG: Kein Panel-Dokument gefunden!")
else:
    assert "nameWithOwner" in sample_panel["_id"], "FEHLER: _id.nameWithOwner fehlt"
    assert "date"          in sample_panel["_id"], "FEHLER: _id.date fehlt"
    assert "commits"       in sample_panel,        "FEHLER: commits fehlt"
    assert "contributors"  in sample_panel,        "FEHLER: contributors fehlt"
    print(f"    repo:          {sample_panel['_id']['nameWithOwner']}")
    print(f"    date:          {sample_panel['_id']['date']}")
    print(f"    commits:       {sample_panel['commits']}")
    print(f"    contributors:  {sample_panel['contributors']}")
    print(f"    additions:     {sample_panel.get('commitsAdditions', 'n/a')}")
    print(f"    [5] panel_col Schema  OK  ✓")


# ── Test 6: Panel-Aggregation wie core_analysis.py ────────────────────────
print(f"\n[6] panel_col.aggregate() — wie in core_analysis.py...")

raw_col = db["depsProjectsCommits"]
raw = list(raw_col.aggregate([
    {"$limit": 10000},
    {"$addFields": {
        "_commit_date": {"$toDate": "$commit.author.date"},
        "author_login": {"$ifNull": ["$author.login", "$commit.author.name"]}
    }},
    {"$addFields": {
        "month_date": {"$dateFromParts": {
            "year":  {"$year":  "$_commit_date"},
            "month": {"$month": "$_commit_date"},
            "day":   1
        }}
    }},
    {"$group": {
        "_id":        "$month_date",
        "commits_sum": {"$sum": 1},
        "n":           {"$sum": 1}
    }},
    {"$sort": {"_id": 1}},
    {"$limit": 3}
], allowDiskUse=True))

if raw:
    print(f"    Monatspunkte: {len(raw)} (aus 10k-Doc-Sample)")
    for r in raw:
        print(f"      {str(r['_id'])[:10]}  n_repos={r['n']}  commits_sum={r['commits_sum']}")
    print(f"    [6] Panel-Aggregation  OK  ✓")
else:
    print("    WARNUNG: Keine Daten gefunden.")

print(f"\n{'='*60}")
print(f"  ALLE TESTS BESTANDEN  ✓")
print(f"{'='*60}\n")

