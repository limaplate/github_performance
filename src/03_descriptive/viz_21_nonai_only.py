"""
viz_21_nonai_only.py — Folie 21 FIX: nur Non-AI Repos (exklusiv)
"""
import json
from datetime import datetime
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pymongo import MongoClient

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.db_config import get_mongo_uri
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.paths import get_output_dir

MONGO_URI = get_mongo_uri()
OUT_DIR = get_output_dir()
KI_MAPPING_PATH = OUT_DIR / "ki_repo_mapping.json"

def ts():
    return datetime.now().strftime("%H:%M:%S")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=20000)
db = client["upstreamPackages"]
db.command("ping")
print(f"[{ts()}] Verbunden.")

with open(KI_MAPPING_PATH, encoding="utf-8") as f:
    ki_data = json.load(f)
ki_mapping  = ki_data.get("repo_mapping", {})
ai_set      = set(ki_mapping.keys())  # alle KI-Repos (native + boosted + unknown)
print(f"[{ts()}] AI-Set (exkludiert): {len(ai_set):,} Repos")

panel = db["depsProjectsPanel"]

# Earliest date NUR fuer Non-AI Repos
print(f"[{ts()}] Berechne Earliest-Date (Non-AI only)...")
earliest_cur = panel.aggregate([
    {"$match": {"_id.nameWithOwner": {"$nin": list(ai_set)}}},
    {"$group": {
        "_id": "$_id.nameWithOwner",
        "first_date": {"$min": "$_id.date"}
    }}
], allowDiskUse=True)

repo_first = {d["_id"]: d["first_date"] for d in earliest_cur}
print(f"[{ts()}] Non-AI Repos: {len(repo_first):,}")

# Buckets befuellen
bucket_commits      = np.zeros(24, dtype=np.float64)
bucket_contributors = np.zeros(24, dtype=np.float64)
bucket_count        = np.zeros(24, dtype=np.int64)

print(f"[{ts()}] Lade Snapshots (Non-AI only)...")
cursor = panel.find(
    {"_id.nameWithOwner": {"$nin": list(ai_set)}},
    {"_id": 1, "commits": 1, "contributors": 1}
)

for doc in cursor:
    repo = doc["_id"]["nameWithOwner"]
    first_date = repo_first.get(repo)
    if first_date is None:
        continue
    try:
        d_doc   = doc["_id"]["date"]
        d_doc   = d_doc if isinstance(d_doc, datetime) else datetime.fromisoformat(str(d_doc))
        d_first = first_date if isinstance(first_date, datetime) else datetime.fromisoformat(str(first_date))
        rel = (d_doc.year - d_first.year) * 12 + (d_doc.month - d_first.month)
    except Exception:
        continue
    if 0 <= rel < 24:
        bucket_commits[rel]      += doc.get("commits", 0) or 0
        bucket_contributors[rel] += doc.get("contributors", 0) or 0
        bucket_count[rel]        += 1

cursor.close()
print(f"[{ts()}] Fertig. Max count: {bucket_count.max():,}")

with np.errstate(invalid="ignore"):
    avg_commits      = np.where(bucket_count > 0, bucket_commits      / bucket_count, 0)
    avg_contributors = np.where(bucket_count > 0, bucket_contributors / bucket_count, 0)

# Plot
fig, ax1 = plt.subplots(figsize=(10, 5))
months = np.arange(24)
ax1.bar(months, avg_commits, color="#4C72B0", alpha=0.85, label="Ø Commits", width=0.7)
ax1.set_ylabel("Ø Commits pro Monat", color="#4C72B0", fontsize=10)
ax1.tick_params(axis="y", labelcolor="#4C72B0")

ax2 = ax1.twinx()
ax2.plot(months, avg_contributors, color="#DD8452", linewidth=2.5,
         marker="o", markersize=4, label="Ø Contributors")
ax2.set_ylabel("Ø Contributors pro Monat", color="#DD8452", fontsize=10)
ax2.tick_params(axis="y", labelcolor="#DD8452")

ax1.set_xlabel("Relativer Monat ab erstem Commit (Monat 0 = Projektstart)", fontsize=10)
ax1.set_title("Aktivität Non-AI Repos – Commits & Contributors\n(normiert auf 24 Monate ab Projektstart, exkl. alle KI-Repos)",
              fontsize=12, fontweight="bold", pad=10)
ax1.spines[["top"]].set_visible(False)
ax1.xaxis.set_major_locator(mticker.MultipleLocator(2))
ax1.set_xticks(range(0, 24, 2))

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", framealpha=0.8)

plt.tight_layout()
out = OUT_DIR / "viz_21_activity_nonai_only.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ts()}] Gespeichert: {out}")
client.close()
