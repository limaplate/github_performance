"""
build_ki_repo_mapping.py — Verknuepft KI-Packages mit GitHub-Repos

Schritte:
  1. Alle KI-Packages aus depsPackages (Signal A + B) laden
  2. Fuer jedes KI-Package: GitHub-Repo-Link aus packageInformation.projects[]
  3. AI-native vs. AI-boosted Label aus depsPackagesDependencies (createdAt)
  4. Ergebnis: JSON mit Repo -> {is_ki, ki_type, ki_year, packages[]}

Output: ki_repo_mapping.json
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
DB_NAME  = "upstreamPackages"
OUT_JSON = Path(__file__).parent / "ki_repo_mapping.json"

# Signal-A Regex (High-Confidence Keywords)
HIGH_CONF_REGEX = (
    r"\bai\b|\bml\b|machine learning|deep learning|reinforcement learning|transfer learning"
    r"|llm\b|llms\b|language model|large language model|generative ai|foundation model|generative model"
    r"|transformer|diffusion model|\bgan\b|\bgans\b|\bvae\b|attention mechanism"
    r"|natural language|\bnlp\b|tokenizer|tokenization|sentiment analysis|text generation"
    r"|text classification|named entity|computer vision|object detection|image classification"
    r"|image segmentation|image generation|text.to.speech|\btts\b|speech recognition"
    r"|chatbot|chat assistant|pre.trained|fine.tuning|vector store|vector search|\brag\b"
    r"|semantic search|retrieval augmented|word embedding|text embedding|prompt engineering"
    r"|\bautoml\b|\bmlops\b|gradient boosting"
    r"|pytorch|openai|tensorflow|langchain|huggingface"
    r"|\bllama\b|\bgpt\b|chatgpt|gpt.3|gpt.4|\bbert\b|gemini|stable diffusion|mistral"
)

# Signal-B Libraries
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


def main():
    print(f"[{ts()}] Verbinde mit MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]
    db.command("ping")
    print(f"[{ts()}] Verbunden.\n")

    packages = db["depsPackages"]
    deps     = db["depsPackagesDependencies"]
    results  = {}

    # ── Block 1: Alle KI-Packages mit Repo-Link ──────────────────────────────
    print(f"[{ts()}] Block 1: KI-Packages mit GitHub-Repo-Link laden...")

    t0 = time.time()
    ki_with_repo = list(packages.find(
        {
            "_id.system": "PYPI",
            "packageInformation.projects": {"$exists": True, "$not": {"$size": 0}},
            "$or": [
                {"packageInformation.description": {"$regex": HIGH_CONF_REGEX, "$options": "i"}},
                {"packageInformation.dependencies.name": {"$in": list(AI_LIBS)}}
            ]
        },
        {
            "_id": 1,
            "packageInformation.projects": 1,
            "packageInformation.createdAt": 1,
        }
    ))
    print(f"  KI-Packages mit Repo-Link: {len(ki_with_repo):>8,}  ({time.time()-t0:.1f}s)")
    results["n_ki_packages_with_repo"] = len(ki_with_repo)

    # ── Block 2: Package-Namen sammeln fuer native/boosted Lookup ────────────
    print(f"\n[{ts()}] Block 2: AI-native vs. AI-boosted klassifizieren...")

    pkg_names = [doc["_id"]["name"] for doc in ki_with_repo]
    print(f"  Klassifiziere {len(pkg_names):,} Packages...")

    # Batch-Aggregation: fuer alle Packages auf einmal
    t0 = time.time()
    classification_raw = list(deps.aggregate([
        {"$match": {
            "_id.name": {"$in": pkg_names},
            "createdAt": {"$exists": True, "$ne": None}
        }},
        {"$sort": {"createdAt": 1}},
        {"$group": {
            "_id": "$_id.name",
            "first_created": {"$first": "$createdAt"},
            "versions": {"$push": {
                "createdAt": "$createdAt",
                "has_ki": {"$cond": [
                    {"$gt": [{"$size": {"$filter": {
                        "input": {"$ifNull": ["$dependencies", []]},
                        "as": "d",
                        "cond": {"$and": [
                            {"$eq": ["$$d.depth", 1]},
                            {"$in": ["$$d.name", list(AI_LIBS)]}
                        ]}
                    }}}, 0]},
                    True, False
                ]}
            }}
        }},
        {"$addFields": {
            "first_ki_created": {
                "$let": {
                    "vars": {"ki_versions": {"$filter": {
                        "input": "$versions",
                        "as": "v",
                        "cond": "$$v.has_ki"
                    }}},
                    "in": {"$min": "$$ki_versions.createdAt"}
                }
            }
        }},
        {"$match": {"first_ki_created": {"$ne": None}}},
        {"$addFields": {
            "ki_type": {"$cond": [
                {"$eq": ["$first_created", "$first_ki_created"]},
                "native", "boosted"
            ]},
            "ki_year": {"$year": {"$convert": {
                "input": {"$multiply": ["$first_ki_created", 1000]},
                "to": "date", "onError": None, "onNull": None
            }}},
            "birth_year": {"$year": {"$convert": {
                "input": {"$multiply": ["$first_created", 1000]},
                "to": "date", "onError": None, "onNull": None
            }}},
            "lag_months": {"$cond": [
                {"$eq": ["$first_created", "$first_ki_created"]},
                0,
                {"$divide": [
                    {"$subtract": ["$first_ki_created", "$first_created"]},
                    2592000
                ]}
            ]}
        }},
        {"$project": {
            "_id": 1,
            "ki_type": 1,
            "ki_year": 1,
            "birth_year": 1,
            "lag_months": 1,
            "first_created": 1,
            "first_ki_created": 1
        }}
    ], allowDiskUse=True))
    print(f"  Klassifizierung abgeschlossen: {len(classification_raw):,}  ({time.time()-t0:.1f}s)")

    # Index: package_name -> classification
    pkg_classification = {d["_id"]: d for d in classification_raw}

    n_native  = sum(1 for d in classification_raw if d["ki_type"] == "native")
    n_boosted = sum(1 for d in classification_raw if d["ki_type"] == "boosted")
    print(f"  AI-native:  {n_native:>8,}  ({100*n_native/len(classification_raw):.1f}%)")
    print(f"  AI-boosted: {n_boosted:>8,}  ({100*n_boosted/len(classification_raw):.1f}%)")
    results["n_classified"] = len(classification_raw)
    results["n_native"]     = n_native
    results["n_boosted"]    = n_boosted

    # ── Block 3: Repo-Mapping aufbauen ───────────────────────────────────────
    print(f"\n[{ts()}] Block 3: Repo-Mapping aufbauen...")

    repo_map = {}  # repo_name -> {...}

    for doc in ki_with_repo:
        pkg_name = doc["_id"]["name"]
        repos    = doc.get("packageInformation", {}).get("projects", [])
        clf      = pkg_classification.get(pkg_name)

        for repo in repos:
            repo_name = repo.get("name")
            if not repo_name:
                continue

            if repo_name not in repo_map:
                repo_map[repo_name] = {
                    "repo": repo_name,
                    "packages": [],
                    "ki_types": [],
                    "ki_years": [],
                }

            repo_map[repo_name]["packages"].append(pkg_name)
            if clf:
                repo_map[repo_name]["ki_types"].append(clf["ki_type"])
                if clf.get("ki_year"):
                    repo_map[repo_name]["ki_years"].append(clf["ki_year"])

    # Finalisiere: bei Repos mit mehreren Packages -> Mehrheitsentscheid
    final_repos = []
    for repo_name, info in repo_map.items():
        types  = info["ki_types"]
        n_nat  = types.count("native")
        n_boo  = types.count("boosted")
        years  = info["ki_years"]

        if types:
            ki_type = "native" if n_nat >= n_boo else "boosted"
        else:
            ki_type = "unknown"

        final_repos.append({
            "repo":        repo_name,
            "ki_type":     ki_type,
            "ki_year":     min(years) if years else None,
            "n_packages":  len(info["packages"]),
            "packages":    info["packages"][:5],
        })

    n_repos_total   = len(final_repos)
    n_repos_native  = sum(1 for r in final_repos if r["ki_type"] == "native")
    n_repos_boosted = sum(1 for r in final_repos if r["ki_type"] == "boosted")
    n_repos_unknown = sum(1 for r in final_repos if r["ki_type"] == "unknown")

    print(f"\n  KI-Repos gesamt:   {n_repos_total:>8,}")
    print(f"  AI-native:         {n_repos_native:>8,}  ({100*n_repos_native/n_repos_total:.1f}%)")
    print(f"  AI-boosted:        {n_repos_boosted:>8,}  ({100*n_repos_boosted/n_repos_total:.1f}%)")
    print(f"  Unbekannt:         {n_repos_unknown:>8,}  ({100*n_repos_unknown/n_repos_total:.1f}%)")

    results["n_ki_repos"]         = n_repos_total
    results["n_ki_repos_native"]  = n_repos_native
    results["n_ki_repos_boosted"] = n_repos_boosted
    results["n_ki_repos_unknown"] = n_repos_unknown

    # ── Block 4: Speichern ───────────────────────────────────────────────────
    print(f"\n[{ts()}] Block 4: Speichern...")

    # Kompaktes Mapping fuer spaetere Joins
    mapping_compact = {
        r["repo"]: {
            "ki_type":    r["ki_type"],
            "ki_year":    r["ki_year"],
            "n_packages": r["n_packages"],
        }
        for r in final_repos
    }

    results["repo_mapping"] = mapping_compact
    results["repo_list_sample"] = final_repos[:20]

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Mapping gespeichert: {OUT_JSON}")
    print(f"  ({n_repos_total:,} KI-Repos, {len(mapping_compact):,} Eintraege)")

    client.close()
    print(f"\n[{ts()}] Fertig.")


if __name__ == "__main__":
    main()
