"""
compat_v2.py — Kompatibilitaetsschicht upstreamPackages (V1) <-> upstreamPackagesV2 (V2)

Kein Schreibzugriff noetig — arbeitet mit reinen Lesezugriffen ueber
Python-Wrapper-Objekte die find_one() und aggregate() emulieren.

Verwendung in jedem Skript — nur 2 Zeilen aendern:
    from common.compat_v2 import get_deps_collection, get_panel_collection
    deps_col  = get_deps_collection(db)   # statt db["depsPackagesDependencies"]
    panel_col = get_panel_collection(db)  # statt db["depsProjectsPanel"]
"""
from __future__ import annotations
from pymongo.database import Database


def detect_db_version(db: Database) -> str:
    try:
        if db["depsPackagesDependencies"].estimated_document_count() > 0:
            return "v1"
    except Exception:
        pass
    return "v2"


# ─────────────────────────────────────────────────────────────────────────────
# Basis-Wrapper: emuliert eine MongoDB-Collection mit find_one() + aggregate()
# ─────────────────────────────────────────────────────────────────────────────

class _CompatCollection:
    def __init__(self, collection, prefix_pipeline: list):
        self._col = collection
        self._prefix = prefix_pipeline
        self.name = collection.name + "_compat"

    # Fields that exist on the RAW source documents (before any $group stage).
    # Filters on these can be pushed before _prefix for index utilisation.
    _SOURCE_FIELDS = {"_id.nameWithOwner"}

    def _split_filter(self, f: dict):
        """Split filter into (pre_match, post_match) where pre can go before _prefix."""
        if not f:
            return {}, {}
        pre  = {k: v for k, v in f.items() if k in self._SOURCE_FIELDS}
        post = {k: v for k, v in f.items() if k not in self._SOURCE_FIELDS}
        return pre, post

    def aggregate(self, pipeline: list, **kwargs):
        # Push _id.nameWithOwner $match stages to before the prefix pipeline
        # so MongoDB can use the index on the raw source collection.
        if pipeline and list(pipeline[0].keys()) == ["$match"]:
            pre, post = self._split_filter(pipeline[0]["$match"])
            rest = pipeline[1:]
            early = [{"$match": pre}] if pre else []
            mid   = [{"$match": post}] if post else []
            return self._col.aggregate(early + self._prefix + mid + rest, **kwargs)
        return self._col.aggregate(self._prefix + pipeline, **kwargs)

    def find_one(self, match_filter: dict = None, *args, **kwargs):
        pre, post = self._split_filter(match_filter or {})
        early = [{"$match": pre}] if pre else []
        mid   = [{"$match": post}] if post else []
        rows = list(self._col.aggregate(
            early + self._prefix + mid + [{"$limit": 1}],
            allowDiskUse=True
        ))
        return rows[0] if rows else None

    def count_documents(self, filter: dict = None, **kwargs):
        pre, post = self._split_filter(filter or {})
        early = [{"$match": pre}] if pre else []
        mid   = [{"$match": post}] if post else []
        pipeline = early + self._prefix + mid + [{"$count": "n"}]
        rows = list(self._col.aggregate(pipeline, allowDiskUse=True))
        return rows[0]["n"] if rows else 0

    def estimated_document_count(self):
        return self._col.estimated_document_count()

    def find(self, filter: dict = None, projection: dict = None, **kwargs):
        """Emuliert Collection.find() als Aggregation-Cursor."""
        pre, post = self._split_filter(filter or {})
        stages = []
        if pre:
            stages.append({"$match": pre})
        stages += list(self._prefix)
        if post:
            stages.append({"$match": post})
        if projection:
            stages.append({"$project": projection})
        return self._col.aggregate(stages, allowDiskUse=True, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 1. DEPS: depsPackagesDependencies (V1) <-> depsVersions (V2)
#
# V1-Schema pro Dokument:
#   { _id: {name, version, system},
#     createdAt: int,           # Unix-Sekunden
#     dependencies: [{name, depth}] }
# ─────────────────────────────────────────────────────────────────────────────

_DEPS_PIPELINE = [
    {"$match": {
        "dependenciesprocessed": True,
        "dependencyerror": {"$ne": True}
    }},
    {"$addFields": {
        # ISO-Datum -> Unix-Sekunden (identisch zu V1)
        "createdAt": {
            "$cond": {
                "if":   {"$gt": ["$upstreampublishedat", None]},
                "then": {"$toLong": {"$divide": [
                            {"$toLong": {"$toDate": "$upstreampublishedat"}},
                            1000
                        ]}},
                "else": None
            }
        },
        # distance (V2) -> depth (V1), package.name -> name
        "dependencies": {
            "$map": {
                "input": {"$ifNull": ["$dependencyInformation.dependencies", []]},
                "as":    "d",
                "in":    {"name": "$$d.package.name", "depth": "$$d.distance"}
            }
        }
    }},
    {"$project": {"_id": 1, "createdAt": 1, "dependencies": 1}}
]


def get_deps_collection(db: Database):
    """
    V1: gibt db["depsPackagesDependencies"] unveraendert zurueck.
    V2: gibt einen Wrapper zurueck der depsVersions mit V1-Schema emuliert.
    """
    if detect_db_version(db) == "v1":
        return db["depsPackagesDependencies"]

    existing = {c["name"] for c in db.list_collections()}
    source = next(
        (s for s in ["depsVersions", "depsVerisons"] if s in existing), None
    )
    if not source:
        raise RuntimeError("depsVersions nicht gefunden — V2-Verbindung pruefen.")

    print(f"[compat_v2] deps -> '{source}' (V2-Wrapper, kein Schreibzugriff noetig)")
    return _CompatCollection(db[source], _DEPS_PIPELINE)


# ─────────────────────────────────────────────────────────────────────────────
# 2. PANEL: depsProjectsPanel (V1) <-> depsProjectsCommits (V2)
#
# V1-Schema pro Dokument:
#   { _id: {nameWithOwner, date},   # date = Monatsanfang
#     commits, contributors, authors, committers,
#     commitsAdditions, commitsDeletions, commitsTotal }
# ─────────────────────────────────────────────────────────────────────────────

_PANEL_PIPELINE = [
    {"$addFields": {
        "_commit_date":    {"$toDate": "$commit.author.date"},
        "author_login":    {"$ifNull": ["$author.login",    "$commit.author.name"]},
        "committer_login": {"$ifNull": ["$committer.login", "$commit.committer.name"]}
    }},
    {"$addFields": {
        "month_date": {
            "$dateFromParts": {
                "year":  {"$year":  "$_commit_date"},
                "month": {"$month": "$_commit_date"},
                "day":   1
            }
        }
    }},
    {"$group": {
        "_id": {
            "nameWithOwner": "$_id.nameWithOwner",
            "date":          "$month_date"
        },
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
    }},
    {"$project": {
        "_id": 1, "commits": 1, "contributors": 1,
        "authors": 1, "committers": 1,
        "commitsAdditions": 1, "commitsDeletions": 1, "commitsTotal": 1
    }}
]


def get_panel_collection(db: Database):
    """
    V1: gibt db["depsProjectsPanel"] unveraendert zurueck.
    V2: gibt einen Wrapper zurueck der depsProjectsCommits monatlich aggregiert.
    """
    if detect_db_version(db) == "v1":
        return db["depsProjectsPanel"]

    existing = {c["name"] for c in db.list_collections()}
    source = next(
        (s for s in ["depsProjectsCommits", "despProjectsCommits"] if s in existing), None
    )
    if not source:
        raise RuntimeError("depsProjectsCommits nicht gefunden — V2-Verbindung pruefen.")

    print(f"[compat_v2] panel -> '{source}' (V2-Wrapper, kein Schreibzugriff noetig)")
    return _CompatCollection(db[source], _PANEL_PIPELINE)


# ─────────────────────────────────────────────────────────────────────────────
# 3. TOPICS: depsProjectsPanel.repoData.topics (V1) <-> depsProjects.repoData.topics (V2)
#
# V1: topics stehen in depsProjectsPanel unter repoData.topics (Zeitreihe → dedup nötig)
# V2: depsProjectsPanel existiert nicht — topics direkt in depsProjects.repoData.topics
#
# Rückgabe-Schema (für beide Versionen gleich):
#   { _id: {nameWithOwner}, topics: [...] }
# ─────────────────────────────────────────────────────────────────────────────

_TOPICS_PIPELINE_V1 = [
    # Panel hat mehrere Einträge pro Repo -> $group für Dedup
    {"$match":  {"repoData.topics": {"$exists": True, "$ne": []}}},
    {"$group":  {
        "_id":    "$_id.nameWithOwner",
        "topics": {"$first": "$repoData.topics"}
    }},
    {"$project": {"_id": 1, "topics": 1}}
]

_TOPICS_PIPELINE_V2 = [
    # depsProjects: ein Dokument pro Repo — topics direkt verfügbar
    {"$match":  {"repoData.topics": {"$exists": True, "$ne": []}}},
    {"$project": {
        "_id":    {"nameWithOwner": "$repoData.nameWithOwner"},
        "topics": "$repoData.topics"
    }}
]


def get_topics_collection(db: Database):
    """
    Signal C: GitHub-Topics.
    V1: aus depsProjectsPanel.repoData.topics  (mit $group für Dedup)
    V2: aus depsProjects.repoData.topics       (ein Dokument pro Repo)

    Rückgabe: _CompatCollection mit Schema { _id: {nameWithOwner}, topics: [...] }
    Verwendung in count_signals.py:
        from common.compat_v2 import get_topics_collection
        topics_col = get_topics_collection(db)  # statt db["depsProjectsPanel"]
    """
    if detect_db_version(db) == "v1":
        print("[compat_v2] topics -> 'depsProjectsPanel' (V1-direkt)")
        return _CompatCollection(db["depsProjectsPanel"], _TOPICS_PIPELINE_V1)

    print("[compat_v2] topics -> 'depsProjects' (V2-Wrapper, repoData.topics)")
    return _CompatCollection(db["depsProjects"], _TOPICS_PIPELINE_V2)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Convenience
# ─────────────────────────────────────────────────────────────────────────────

def setup_v2_views(db: Database):
    """Abwaertskompatibel — tut in V2 nichts mehr (kein Schreibzugriff noetig)."""
    version = detect_db_version(db)
    if version == "v1":
        print("[compat_v2] V1-Datenbank — nichts zu tun.")
    else:
        print("[compat_v2] V2-Datenbank — Wrapper-Modus aktiv (kein Schreibzugriff noetig).")

