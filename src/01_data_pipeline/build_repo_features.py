"""
build_repo_features.py

Zieht alle relevanten Variablen pro Repo aus MongoDB und speichert als:
  repo_features.csv       — Basis fuer Korrelationsmatrix + OLS
  repo_features_log.txt  — Laufprotokoll

Variablen:
  repo              — owner/repo (nameWithOwner)
  ki_type           — non_ai / native / boosted
  native_i          — 1 wenn native
  boosted_i         — 1 wenn boosted
  stars             — repoData.stars
  log_stars         — log(1 + stars)
  age_months        — Monate seit created_at bis heute
  org_i             — 1 wenn Organization
  license_cat       — Permissiv / Copyleft / Andere
  perm_i            — 1 wenn Permissiv
  commits_median    — Median commits ueber alle Panel-Snapshots
  contributors_median — Median contributors ueber alle Panel-Snapshots
  commits_total     — Summe aller commits
  n_snapshots       — Anzahl Panel-Snapshots
  forks             — repoData.forks (falls vorhanden)
"""

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import csv

from pymongo import MongoClient

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.db_config import get_mongo_uri
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.paths import get_output_dir

import argparse as _argparse
_p = _argparse.ArgumentParser(add_help=False)
_p.add_argument("--mongo-db", default="upstreamPackages")
_args, _ = _p.parse_known_args()

MONGO_URI = get_mongo_uri()
DB_NAME   = _args.mongo_db
OUT_DIR = get_output_dir()
OUT_CSV        = OUT_DIR / "repo_features.csv"
KI_MAPPING_PATH = OUT_DIR / "ki_repo_mapping.json"
NOW            = datetime(2026, 6, 9, tzinfo=timezone.utc)

PERMISSIVE_SPDX = {
    "MIT", "Apache-2.0", "Apache-1.1",
    "BSD-2-Clause", "BSD-3-Clause", "BSD-3-Clause-Clear", "BSD-4-Clause",
    "ISC", "0BSD", "Unlicense", "CC0-1.0", "WTFPL",
    "PSF-2.0", "Python-2.0", "Zlib", "MPL-2.0",
    "LGPL-2.0", "LGPL-2.1", "LGPL-2.1-only", "LGPL-2.1-or-later",
    "LGPL-3.0", "LGPL-3.0-only", "LGPL-3.0-or-later",
}
COPYLEFT_SPDX = {
    "GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-2.0+",
    "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later", "GPL-3.0+",
    "AGPL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later",
    "EUPL-1.1", "EUPL-1.2",
}
PERMISSIVE_PATTERNS = [
    "mit", "apache", "bsd", "isc", "unlicense", "wtfpl", "mpl",
    "lgpl", "mozilla public", "boost software", "zlib",
    "python software foundation", "artistic", "cc0", "creative commons zero",
]
COPYLEFT_PATTERNS = ["gpl", "agpl", "eupl", "gnu general", "gnu affero"]


def ts():
    return datetime.now().strftime("%H:%M:%S")


def classify_license(spdx):
    if not spdx:
        return "Andere"
    s = str(spdx).strip()
    sl = s.lower()
    if sl in ("noassertion", "unknown", "none", "other", ""):
        return "Andere"
    if s in PERMISSIVE_SPDX:
        return "Permissiv"
    if s in COPYLEFT_SPDX:
        return "Copyleft"
    for p in PERMISSIVE_PATTERNS:
        if p in sl:
            return "Permissiv"
    for c in COPYLEFT_PATTERNS:
        if c in sl:
            return "Copyleft"
    return "Andere"


def age_months(created_at):
    """Monate zwischen created_at und NOW."""
    if created_at is None:
        return None
    try:
        if isinstance(created_at, datetime):
            dt = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
        elif isinstance(created_at, (int, float)):
            dt = datetime.fromtimestamp(created_at, tz=timezone.utc)
        elif isinstance(created_at, str):
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            return None
        diff = (NOW.year - dt.year) * 12 + (NOW.month - dt.month)
        return max(0, diff)
    except Exception:
        return None


# ── MongoDB verbinden ────────────────────────────────────────────────────────
print(f"[{ts()}] Verbinde MongoDB...")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=20000)
db = client[DB_NAME]
db.command("ping")
print(f"[{ts()}] Verbunden.")

from common.compat_v2 import get_panel_collection
projects = db["depsProjects"]
panel    = get_panel_collection(db)

# ── KI-Mapping laden ─────────────────────────────────────────────────────────
with open(KI_MAPPING_PATH, encoding="utf-8") as f:
    ki_data = json.load(f)
ki_mapping       = ki_data.get("repo_mapping", {})
ki_mapping_lower = {k.lower(): v for k, v in ki_mapping.items()}
native_set  = {r for r, v in ki_mapping.items() if v["ki_type"] == "native"}
boosted_set = {r for r, v in ki_mapping.items() if v["ki_type"] == "boosted"}
ai_set      = set(ki_mapping.keys())
print(f"[{ts()}] Mapping: {len(native_set):,} native, {len(boosted_set):,} boosted")

# ── Schritt 1: Panel-Statistiken pro Repo ────────────────────────────────────
# commits_median, contributors_median, commits_total, n_snapshots
print(f"[{ts()}] Schritt 1: Panel-Aggregation (commits, contributors)...")
panel_stats = {}  # repo -> dict

cursor = panel.aggregate([
    {"$group": {
        "_id": "$_id.nameWithOwner",
        "commits_list":      {"$push": "$commits"},
        "contributors_list": {"$push": "$contributors"},
        "commits_sum":       {"$sum": {"$ifNull": ["$commits", 0]}},
        "n_snapshots":       {"$sum": 1},
        "first_commit_date": {"$min": "$_id.date"}
    }}
], allowDiskUse=True)

def _median(lst):
    lst = [v for v in lst if v is not None]
    if not lst:
        return None
    s = sorted(lst)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n//2 - 1] + s[n//2]) / 2

for doc in cursor:
    panel_stats[doc["_id"].lower()] = {
        "commits_median":      _median(doc["commits_list"]),
        "contributors_median": _median(doc["contributors_list"]),
        "commits_total":       doc["commits_sum"],
        "n_snapshots":         doc["n_snapshots"],
        "first_commit_date":   doc.get("first_commit_date"),
    }
print(f"[{ts()}] Panel-Stats: {len(panel_stats):,} Repos")

# ── Schritt 2: depsProjects — statische Metadaten ────────────────────────────
print(f"[{ts()}] Schritt 2: depsProjects laden (stars, age, org, license, forks)...")

# Pruefen welche Felder created_at-artig heissen
sample = projects.find_one({"repoData": {"$exists": True}})
if sample:
    rd = sample.get("repoData", {})
    print(f"  repoData-Felder im Sample: {list(rd.keys())[:20]}")

rows = []
processed = 0

cursor2 = projects.find(
    {},
    {
        "name": 1,
        "repoData.stars":      1,
        "repoData.forks":      1,
        "repoData.license":    1,
        "repoData.created_at": 1,  # V1
        "repoData.createdAt":  1,  # V1 alt
        "repoData.pushedAt":   1,  # V1
        "ownerData.type":      1,
        "stars":               1,
        "license":             1,
        "forks":               1,  # V2 top-level
        "exportDate":          1,  # V2 fallback fuer age (nur grob)
    }
)

for doc in cursor2:
    repo_lower = doc.get("name", "")
    if not repo_lower:
        continue

    # KI-Typ bestimmen (ki_mapping keys sind case-sensitive owner/repo)
    # depsProjects.name ist lowercase — matchen via lower()
    ki_type = "non_ai"
    native_i  = 0
    boosted_i = 0
    entry = ki_mapping_lower.get(repo_lower)
    if entry:
        if entry["ki_type"] == "native":
            ki_type, native_i = "native", 1
        elif entry["ki_type"] == "boosted":
            ki_type, boosted_i = "boosted", 1

    rd = doc.get("repoData") or {}

    # Stars
    stars = rd.get("stars")
    if stars is None:
        stars = doc.get("stars")
    stars = int(stars) if isinstance(stars, (int, float)) else None

    # Forks — V1: repoData.forks, V2: top-level forks
    forks = rd.get("forks")
    if forks is None:
        forks = doc.get("forks")
    forks = int(forks) if isinstance(forks, (int, float)) else None

    # Age — V1: repoData.created_at; V2: Fallback auf ersten Commit-Monat aus Panel
    created = rd.get("created_at") or rd.get("createdAt")
    if created is None:
        created = (panel_stats.get(repo_lower) or {}).get("first_commit_date")
    age = age_months(created)

    # Org
    owner_type = (doc.get("ownerData") or {}).get("type", "")
    org_i = 1 if owner_type == "Organization" else 0

    # License
    lic_raw = rd.get("license") or doc.get("license")
    lic_cat = classify_license(lic_raw)
    perm_i  = 1 if lic_cat == "Permissiv" else 0

    # Panel-Stats joinen
    ps = panel_stats.get(repo_lower, {})

    log_stars = math.log1p(stars) if stars is not None else None

    rows.append({
        "repo":                repo_lower,
        "ki_type":             ki_type,
        "native_i":            native_i,
        "boosted_i":           boosted_i,
        "stars":               stars,
        "log_stars":           round(log_stars, 4) if log_stars is not None else None,
        "age_months":          age,
        "org_i":               org_i,
        "license_cat":         lic_cat,
        "perm_i":              perm_i,
        "commits_median":      ps.get("commits_median"),
        "contributors_median": ps.get("contributors_median"),
        "commits_total":       ps.get("commits_total"),
        "n_snapshots":         ps.get("n_snapshots"),
        "forks":               forks,
    })

    processed += 1
    if processed % 50000 == 0:
        print(f"[{ts()}]   {processed:,} Docs verarbeitet...")

cursor2.close()
print(f"[{ts()}] {len(rows):,} Repos total")

# ── Schritt 3: CSV speichern ─────────────────────────────────────────────────
FIELDS = [
    "repo", "ki_type", "native_i", "boosted_i",
    "stars", "log_stars", "age_months", "org_i",
    "license_cat", "perm_i",
    "commits_median", "contributors_median", "commits_total", "n_snapshots",
    "forks"
]

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)

print(f"[{ts()}] CSV gespeichert: {OUT_CSV}")

# Kurze Zusammenfassung
kis  = [r for r in rows if r["ki_type"] != "non_ai"]
non  = [r for r in rows if r["ki_type"] == "non_ai"]
nat  = [r for r in rows if r["ki_type"] == "native"]
boo  = [r for r in rows if r["ki_type"] == "boosted"]
print(f"\n  Gesamt:     {len(rows):,}")
print(f"  Non-AI:     {len(non):,}")
print(f"  AI-native:  {len(nat):,}")
print(f"  AI-boosted: {len(boo):,}")
print(f"  Mit Stars:  {sum(1 for r in rows if r['stars'] is not None):,}")
print(f"  Mit Age:    {sum(1 for r in rows if r['age_months'] is not None):,}")
print(f"  Mit Panel:  {sum(1 for r in rows if r['n_snapshots'] is not None):,}")

client.close()
print(f"\n[{ts()}] Fertig.")
