"""
viz_29_stars_v2.py — Stars-Vergleich Non-AI vs. AI-Born vs. AI-Boosted
Median-Balken + Durchschnitt als Punkt
"""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=20000)
db = client["upstreamPackages"]
db.command("ping")
print("Verbunden.")

with open(KI_MAPPING_PATH, encoding="utf-8") as f:
    ki_data = json.load(f)
ki_mapping = ki_data.get("repo_mapping", {})
native_set  = {r for r, v in ki_mapping.items() if v["ki_type"] == "native"}
boosted_set = {r for r, v in ki_mapping.items() if v["ki_type"] == "boosted"}

groups = {"non_ai": [], "ai_native": [], "ai_boosted": []}

print("Lade Stars aus depsProjects...")
cursor = db["depsProjects"].find({}, {"_id": 1, "repoData.stars": 1})
for doc in cursor:
    repo = doc["_id"].get("name", "")
    stars = (doc.get("repoData") or {}).get("stars")
    if stars is None or stars < 0:
        continue
    if repo in native_set:
        groups["ai_native"].append(stars)
    elif repo in boosted_set:
        groups["ai_boosted"].append(stars)
    else:
        groups["non_ai"].append(stars)
cursor.close()
client.close()

labels   = ["Non-AI", "AI-Born\n(Native)", "AI-Boosted"]
keys     = ["non_ai", "ai_native", "ai_boosted"]
colors   = ["#4C72B0", "#55A868", "#C44E52"]

medians  = [np.median(groups[k]) for k in keys]
means    = [np.mean(groups[k])   for k in keys]
ns       = [len(groups[k])       for k in keys]

fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(labels, medians, color=colors, alpha=0.85, width=0.5, zorder=2)

# Durchschnitt als Raute
for i, (m, mn) in enumerate(zip(medians, means)):
    ax.plot(i, mn, marker="D", color="black", markersize=7, zorder=3,
            label="Ø (Durchschnitt)" if i == 0 else "")
    ax.annotate(f"Ø {mn:,.0f}", xy=(i, mn), xytext=(10, 4),
                textcoords="offset points", fontsize=8, color="black")

# Median-Werte direkt auf Balken
for bar, med in zip(bars, medians):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
            f"Median: {med:,.0f}", ha="center", va="bottom", fontsize=9, fontweight="bold")

# n unter den Labels
for i, n in enumerate(ns):
    ax.text(i, -ax.get_ylim()[1]*0.06, f"n = {n:,}", ha="center", fontsize=8, color="gray")

ax.set_ylabel("GitHub Stars", fontsize=10)
ax.set_title("Stars-Vergleich: Non-AI vs. AI-Born vs. AI-Boosted\n(Median-Balken + Ø als Raute)",
             fontsize=12, fontweight="bold", pad=10)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", alpha=0.3, zorder=0)
ax.legend(loc="upper right", framealpha=0.8)
ax.set_ylim(bottom=0)

plt.tight_layout()
out = OUT_DIR / "viz_29_stars_v2.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Gespeichert: {out}")
