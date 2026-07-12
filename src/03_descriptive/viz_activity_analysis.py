"""
viz_activity_analysis.py

Erstellt 4 Visualisierungen:
  viz_21_activity_all_repos.png       — Folie 21: Commits & Contributors aller Repos (normiert auf 24 Monate ab erstem Commit)
  viz_23_activity_boosted_prepost.png — Folie 23: AI-Boosted 12 Monate pre & post KI-Integration
  viz_25_activity_born_first24.png    — Folie 25: AI-Born erste 24 Monate
  viz_27_29_orga_stars.png            — Folie 27+29: Orga vs. Privat & Stars (Non-AI vs. AI)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
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
OUT_DIR   = get_output_dir()
KI_MAPPING_PATH = OUT_DIR / "ki_repo_mapping.json"

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def ts():
    return datetime.now().strftime("%H:%M:%S")


def style_ax(ax, title, xlabel, ylabel):
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)


# ── MongoDB ───────────────────────────────────────────────────────────────────

print(f"[{ts()}] Verbinde MongoDB...")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=20000)
db = client[DB_NAME]
db.command("ping")
print(f"[{ts()}] Verbunden.")

from common.compat_v2 import get_panel_collection
panel = get_panel_collection(db)
projects = db["depsProjects"]

# ── KI-Mapping laden ─────────────────────────────────────────────────────────

with open(KI_MAPPING_PATH, encoding="utf-8") as f:
    ki_data = json.load(f)
ki_mapping = ki_data.get("repo_mapping", {})
native_set  = {r for r, v in ki_mapping.items() if v["ki_type"] == "native"}
boosted_set = {r for r, v in ki_mapping.items() if v["ki_type"] == "boosted"}
ai_set      = native_set | boosted_set
non_ai_panel_repos = None  # lazy

print(f"[{ts()}] KI-Mapping: {len(native_set):,} native, {len(boosted_set):,} boosted")

# ═══════════════════════════════════════════════════════════════════════════════
# FOLIE 21 — Aktivität ALLE Repos (normiert 24 Monate ab erstem Commit)
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n[{ts()}] FOLIE 21: Lade Panel-Daten für Normierung auf 24 Monate...")

# Aggregation: pro Repo alle Snapshots, sortiert nach Datum
# Schritt 1: Pro Repo frühestes Datum bestimmen
print(f"[{ts()}]   Berechne Earliest-Date pro Repo...")
earliest = list(panel.aggregate([
    {"$group": {
        "_id": "$_id.nameWithOwner",
        "first_date": {"$min": "$_id.date"}
    }}
], allowDiskUse=True))
print(f"[{ts()}]   {len(earliest):,} Repos")

# Index: repo -> first_date
repo_first = {d["_id"]: d["first_date"] for d in earliest}

# Schritt 2: Alle Panel-Docs abrufen (nur commits + contributors + date + repo)
# Wir machen das als Cursor, um RAM zu schonen
print(f"[{ts()}]   Lade alle Snapshots (commits, contributors)...")

bucket_commits      = np.zeros(24, dtype=np.float64)
bucket_contributors = np.zeros(24, dtype=np.float64)
bucket_count        = np.zeros(24, dtype=np.int64)

cursor = panel.find(
    {},
    {"_id": 1, "commits": 1, "contributors": 1}
)

for doc in cursor:
    repo = doc["_id"]["nameWithOwner"]
    doc_date = doc["_id"]["date"]
    first_date = repo_first.get(repo)
    if first_date is None:
        continue
    # Relativer Monat (0-basiert)
    try:
        d_doc   = doc_date if isinstance(doc_date, datetime) else datetime.fromisoformat(str(doc_date))
        d_first = first_date if isinstance(first_date, datetime) else datetime.fromisoformat(str(first_date))
        # Monats-Differenz
        rel_month = (d_doc.year - d_first.year) * 12 + (d_doc.month - d_first.month)
    except Exception:
        continue
    if 0 <= rel_month < 24:
        commits      = doc.get("commits", 0) or 0
        contributors = doc.get("contributors", 0) or 0
        bucket_commits[rel_month]      += commits
        bucket_contributors[rel_month] += contributors
        bucket_count[rel_month]        += 1

cursor.close()

# Durchschnitt pro Bucket
with np.errstate(invalid="ignore"):
    avg_commits      = np.where(bucket_count > 0, bucket_commits      / bucket_count, 0)
    avg_contributors = np.where(bucket_count > 0, bucket_contributors / bucket_count, 0)

print(f"[{ts()}]   Buckets befüllt. Max count: {bucket_count.max():,}")

# Plot
fig, ax1 = plt.subplots(figsize=(10, 5))
months = np.arange(24)
ax1.bar(months, avg_commits, color="#4C72B0", alpha=0.85, label="Ø Commits", width=0.7)
ax1.set_ylabel("Ø Commits pro Monat", color="#4C72B0", fontsize=10)
ax1.tick_params(axis="y", labelcolor="#4C72B0")

ax2 = ax1.twinx()
ax2.plot(months, avg_contributors, color="#DD8452", linewidth=2.5, marker="o", markersize=4, label="Ø Contributors")
ax2.set_ylabel("Ø Contributors pro Monat", color="#DD8452", fontsize=10)
ax2.tick_params(axis="y", labelcolor="#DD8452")

ax1.set_xlabel("Relativer Monat ab erstem Commit / Release (Monat 0 = Start)", fontsize=10)
ax1.set_title("Aktivität aller Repos – Commits & Contributors (normiert auf 24 Monate ab Projektstart)",
              fontsize=12, fontweight="bold", pad=10)
ax1.spines[["top"]].set_visible(False)
ax1.set_xticks(months)
ax1.xaxis.set_major_locator(mticker.MultipleLocator(2))

# Kombinierte Legende
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", framealpha=0.8)

plt.tight_layout()
out = OUT_DIR / "viz_21_activity_all_repos.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ts()}]   Gespeichert: {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# FOLIE 23 — AI-Boosted: 12 Monate pre & post KI-Integration
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n[{ts()}] FOLIE 23: AI-Boosted pre/post...")

boosted_with_year = {r: v["ki_year"] for r, v in ki_mapping.items()
                     if v["ki_type"] == "boosted" and v["ki_year"] is not None}
print(f"[{ts()}]   Boosted-Repos mit ki_year: {len(boosted_with_year):,}")

bucket_b_commits      = np.zeros(25, dtype=np.float64)  # -12 bis +12
bucket_b_contributors = np.zeros(25, dtype=np.float64)
bucket_b_count        = np.zeros(25, dtype=np.int64)

boosted_list = list(boosted_with_year.keys())
BATCH = 1000
for i in range(0, len(boosted_list), BATCH):
    batch = boosted_list[i:i+BATCH]
    cursor = panel.find(
        {"_id.nameWithOwner": {"$in": batch}},
        {"_id": 1, "commits": 1, "contributors": 1}
    )
    for doc in cursor:
        repo = doc["_id"]["nameWithOwner"]
        ki_year = boosted_with_year.get(repo)
        if ki_year is None:
            continue
        doc_date = doc["_id"]["date"]
        try:
            d = doc_date if isinstance(doc_date, datetime) else datetime.fromisoformat(str(doc_date))
            # Relativer Monat: 0 = Monat der KI-Integration (Jan ki_year)
            rel = (d.year - ki_year) * 12 + d.month  # +1 bis +12 = post, -11 bis 0 = pre
            # Wir wollen Monat -12 bis +12 relativ zu Jan ki_year
            # Monat 0 = Dezember des Jahres davor
            # rel: Jan ki_year = +1, also offset: -12..+12 entspricht rel -11..+13
            idx = rel + 11  # rel -12 -> idx -1 (skip), rel -11 -> idx 0
            if 0 <= idx < 25:
                bucket_b_commits[idx]      += doc.get("commits", 0) or 0
                bucket_b_contributors[idx] += doc.get("contributors", 0) or 0
                bucket_b_count[idx]        += 1
        except Exception:
            continue
    cursor.close()
    if (i // BATCH) % 5 == 0:
        print(f"[{ts()}]   Batch {i//BATCH + 1}...")

with np.errstate(invalid="ignore"):
    avg_b_commits      = np.where(bucket_b_count > 0, bucket_b_commits      / bucket_b_count, 0)
    avg_b_contributors = np.where(bucket_b_count > 0, bucket_b_contributors / bucket_b_count, 0)

rel_axis = np.arange(-11, 14)  # -11 bis +13 → 25 Werte, Monat 0 = Dez vor ki_year
# Vereinfacht: Achsenlabels -12 bis +12
fig, ax1 = plt.subplots(figsize=(11, 5))
ax1.bar(rel_axis, avg_b_commits, color="#4C72B0", alpha=0.85, label="Ø Commits", width=0.7)
ax1.axvline(0, color="red", linewidth=1.5, linestyle="--", label="KI-Integration")
ax1.set_ylabel("Ø Commits pro Monat", color="#4C72B0", fontsize=10)
ax1.tick_params(axis="y", labelcolor="#4C72B0")

ax2 = ax1.twinx()
ax2.plot(rel_axis, avg_b_contributors, color="#DD8452", linewidth=2.5, marker="o", markersize=4, label="Ø Contributors")
ax2.set_ylabel("Ø Contributors pro Monat", color="#DD8452", fontsize=10)
ax2.tick_params(axis="y", labelcolor="#DD8452")

ax1.set_xlabel("Relativer Monat zur KI-Integration (0 = Integrationsjahr Jan)", fontsize=10)
ax1.set_title("Aktivität AI-Boosted Repos – 12 Monate pre & post KI-Integration",
              fontsize=12, fontweight="bold", pad=10)
ax1.spines[["top"]].set_visible(False)
ax1.set_xticks(rel_axis[::2])

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", framealpha=0.8)

plt.tight_layout()
out = OUT_DIR / "viz_23_activity_boosted_prepost.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ts()}]   Gespeichert: {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# FOLIE 25 — AI-Born: erste 24 Monate (normiert ab erstem Commit)
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n[{ts()}] FOLIE 25: AI-Born erste 24 Monate...")

native_list = list(native_set)
bucket_n_commits      = np.zeros(24, dtype=np.float64)
bucket_n_contributors = np.zeros(24, dtype=np.float64)
bucket_n_count        = np.zeros(24, dtype=np.int64)

# Earliest per native repo
native_earliest = {d["_id"]: d["first_date"] for d in earliest if d["_id"] in native_set}

for i in range(0, len(native_list), BATCH):
    batch = native_list[i:i+BATCH]
    cursor = panel.find(
        {"_id.nameWithOwner": {"$in": batch}},
        {"_id": 1, "commits": 1, "contributors": 1}
    )
    for doc in cursor:
        repo = doc["_id"]["nameWithOwner"]
        first_date = native_earliest.get(repo)
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
            bucket_n_commits[rel]      += doc.get("commits", 0) or 0
            bucket_n_contributors[rel] += doc.get("contributors", 0) or 0
            bucket_n_count[rel]        += 1
    cursor.close()
    if (i // BATCH) % 5 == 0:
        print(f"[{ts()}]   Batch {i//BATCH + 1}...")

with np.errstate(invalid="ignore"):
    avg_n_commits      = np.where(bucket_n_count > 0, bucket_n_commits      / bucket_n_count, 0)
    avg_n_contributors = np.where(bucket_n_count > 0, bucket_n_contributors / bucket_n_count, 0)

fig, ax1 = plt.subplots(figsize=(10, 5))
months = np.arange(24)
ax1.bar(months, avg_n_commits, color="#55A868", alpha=0.85, label="Ø Commits", width=0.7)
ax1.set_ylabel("Ø Commits pro Monat", color="#55A868", fontsize=10)
ax1.tick_params(axis="y", labelcolor="#55A868")

ax2 = ax1.twinx()
ax2.plot(months, avg_n_contributors, color="#C44E52", linewidth=2.5, marker="o", markersize=4, label="Ø Contributors")
ax2.set_ylabel("Ø Contributors pro Monat", color="#C44E52", fontsize=10)
ax2.tick_params(axis="y", labelcolor="#C44E52")

ax1.set_xlabel("Relativer Monat ab erstem Commit (Monat 0 = Start)", fontsize=10)
ax1.set_title("Aktivität AI-Born Repos – erste 24 Monate ab Projektstart",
              fontsize=12, fontweight="bold", pad=10)
ax1.spines[["top"]].set_visible(False)
ax1.set_xticks(months)
ax1.xaxis.set_major_locator(mticker.MultipleLocator(2))

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", framealpha=0.8)

plt.tight_layout()
out = OUT_DIR / "viz_25_activity_born_first24.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ts()}]   Gespeichert: {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# FOLIE 27 + 29 — Orga vs. Privat & Stars: Non-AI vs. AI
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n[{ts()}] FOLIE 27+29: Orga vs. Privat & Stars...")

# Alle depsProjects: ownerData.type und stars
print(f"[{ts()}]   Lade depsProjects...")
cursor = projects.find(
    {},
    {"_id": 1, "repoData.stars": 1, "stars": 1, "ownerData.type": 1}
)

groups = {"non_ai": {"org": 0, "user": 0, "stars": []},
          "ai_native": {"org": 0, "user": 0, "stars": []},
          "ai_boosted": {"org": 0, "user": 0, "stars": []}}

for doc in cursor:
    repo = doc["_id"].get("name", "")
    owner_type = (doc.get("ownerData") or {}).get("type", "").lower()
    stars = (doc.get("repoData") or {}).get("stars") or doc.get("stars") or 0

    if repo in native_set:
        grp = "ai_native"
    elif repo in boosted_set:
        grp = "ai_boosted"
    else:
        grp = "non_ai"

    if owner_type == "organization":
        groups[grp]["org"] += 1
    elif owner_type == "user":
        groups[grp]["user"] += 1

    if stars is not None and stars >= 0:
        groups[grp]["stars"].append(stars)

cursor.close()

# ── Plot 27: Orga vs. Privat ─────────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(12, 5))
titles = ["Non-AI", "AI-Born (Native)", "AI-Boosted"]
colors = [["#4C72B0", "#DD8452"], ["#55A868", "#C44E52"], ["#8172B2", "#937860"]]

for ax, (grp_key, title, clrs) in zip(axes, [
    ("non_ai", "Non-AI", colors[0]),
    ("ai_native", "AI-Born (Native)", colors[1]),
    ("ai_boosted", "AI-Boosted", colors[2])
]):
    grp = groups[grp_key]
    total = grp["org"] + grp["user"]
    if total == 0:
        ax.text(0.5, 0.5, "keine Daten", ha="center", va="center")
        continue
    pct_org  = 100 * grp["org"]  / total
    pct_user = 100 * grp["user"] / total
    bars = ax.bar(["Organisation", "Privat"], [pct_org, pct_user], color=clrs, width=0.5)
    for bar, val in zip(bars, [pct_org, pct_user]):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_ylabel("Anteil (%)" if ax == axes[0] else "", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.text(0.5, -0.15, f"n = {total:,}", transform=ax.transAxes, ha="center", fontsize=8, color="gray")

fig.suptitle("Governance-Struktur: Organisation vs. Privat (Non-AI / AI-Born / AI-Boosted)",
             fontsize=13, fontweight="bold", y=1.01)
plt.tight_layout()
out = OUT_DIR / "viz_27_orga_vs_privat.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ts()}]   Gespeichert: {out}")

# ── Plot 29: Stars ───────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))

star_data = []
star_labels = []
star_colors = []
for grp_key, label, color in [
    ("non_ai",     "Non-AI",          "#4C72B0"),
    ("ai_native",  "AI-Born (Native)", "#55A868"),
    ("ai_boosted", "AI-Boosted",       "#C44E52")
]:
    s = groups[grp_key]["stars"]
    if s:
        # Log+1 für bessere Darstellung
        star_data.append(np.log1p(s))
        star_labels.append(f"{label}\n(n={len(s):,})")
        star_colors.append(color)

bp = ax.boxplot(star_data, labels=star_labels, patch_artist=True, notch=False,
                medianprops={"color": "black", "linewidth": 2})
for patch, color in zip(bp["boxes"], star_colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

ax.set_ylabel("log(1 + Stars)", fontsize=10)
ax.set_title("Stars-Verteilung: Non-AI vs. AI-Born vs. AI-Boosted",
             fontsize=12, fontweight="bold", pad=10)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
out = OUT_DIR / "viz_29_stars_distribution.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ts()}]   Gespeichert: {out}")

# ═══════════════════════════════════════════════════════════════════════════════
# FOLIE 21b — Non-AI Repos (exklusiv, normiert 24 Monate ab erstem Commit)
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n[{ts()}] FOLIE 21b: Non-AI Aktivitaet (exklusiv)...")

bucket_na_commits      = np.zeros(24, dtype=np.float64)
bucket_na_contributors = np.zeros(24, dtype=np.float64)
bucket_na_count        = np.zeros(24, dtype=np.int64)

non_ai_earliest = {repo: date for repo, date in repo_first.items()
                   if repo not in ai_set}
print(f"[{ts()}]   Non-AI Repos: {len(non_ai_earliest):,}")

cursor = panel.find(
    {"_id.nameWithOwner": {"$nin": list(ai_set)}},
    {"_id": 1, "commits": 1, "contributors": 1}
)
for doc in cursor:
    repo       = doc["_id"]["nameWithOwner"]
    first_date = non_ai_earliest.get(repo)
    if first_date is None:
        continue
    try:
        d_doc   = doc["_id"]["date"]
        d_doc   = d_doc if isinstance(d_doc, datetime) else datetime.fromisoformat(str(d_doc))
        d_first = first_date if isinstance(first_date, datetime) else datetime.fromisoformat(str(first_date))
        rel     = (d_doc.year - d_first.year) * 12 + (d_doc.month - d_first.month)
    except Exception:
        continue
    if 0 <= rel < 24:
        bucket_na_commits[rel]      += doc.get("commits", 0) or 0
        bucket_na_contributors[rel] += doc.get("contributors", 0) or 0
        bucket_na_count[rel]        += 1
cursor.close()
print(f"[{ts()}]   Non-AI Buckets. Max count: {bucket_na_count.max():,}")

with np.errstate(invalid="ignore"):
    avg_na_commits      = np.where(bucket_na_count > 0, bucket_na_commits      / bucket_na_count, 0)
    avg_na_contributors = np.where(bucket_na_count > 0, bucket_na_contributors / bucket_na_count, 0)

fig, ax1 = plt.subplots(figsize=(10, 5))
months = np.arange(24)
ax1.bar(months, avg_na_commits, color="#4C72B0", alpha=0.85, label="Ø Commits", width=0.7)
ax1.set_ylabel("Ø Commits pro Monat", color="#4C72B0", fontsize=10)
ax1.tick_params(axis="y", labelcolor="#4C72B0")
ax2 = ax1.twinx()
ax2.plot(months, avg_na_contributors, color="#DD8452", linewidth=2.5,
         marker="o", markersize=4, label="Ø Contributors")
ax2.set_ylabel("Ø Contributors pro Monat", color="#DD8452", fontsize=10)
ax2.tick_params(axis="y", labelcolor="#DD8452")
ax1.set_xlabel("Relativer Monat ab erstem Commit (Monat 0 = Projektstart)", fontsize=10)
ax1.set_title("Aktivität Non-AI Repos – Commits & Contributors\n"
              "(normiert auf 24 Monate ab Projektstart, exkl. alle KI-Repos)",
              fontsize=12, fontweight="bold", pad=10)
ax1.spines[["top"]].set_visible(False)
ax1.xaxis.set_major_locator(mticker.MultipleLocator(2))
ax1.set_xticks(range(0, 24, 2))
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", framealpha=0.8)
plt.tight_layout()
out = OUT_DIR / "viz_21b_activity_nonai_only.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ts()}]   Gespeichert: {out}")

# ── Fertig ────────────────────────────────────────────────────────────────────
client.close()
print(f"\n[{ts()}] Alle Visualisierungen fertig.")
print("  viz_21_activity_all_repos.png")
print("  viz_21b_activity_nonai_only.png")
print("  viz_23_activity_boosted_prepost.png")
print("  viz_25_activity_born_first24.png")
print("  viz_27_orga_vs_privat.png")
print("  viz_29_stars_distribution.png")
