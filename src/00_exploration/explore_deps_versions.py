"""
explore_deps_versions.py — Erkundet depsPackagesDependencies fuer AI-native vs. AI-boosted

Fragen:
  1. Wie viele Eintraege hat die Collection? Wie viele distinct Packages?
  2. Ist uploadedAt befuellt? Bei wie vielen Eintraegen?
  3. Wie viele Versionen hat ein Package im Schnitt?
  4. Beispiel: alle Versionen von "transformers" mit Timestamps + KI-Deps
  5. Wie viele unserer 37.970 KI-Packages haben ueberhaupt mehrere Versionen?
  6. Pilot: Fuer 1000 KI-Packages -> erste Version MIT KI-Dep vs. erste Version gesamt
     -> Anteil AI-native vs. AI-boosted schaetzen
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
from common.paths import get_output_dir

MONGO_URI = get_mongo_uri()
DB_NAME = _args.mongo_db
OUT_JSON = Path(get_output_dir()) / "explore_deps_versions_results.json"

# KI-Libraries fuer Matching (Tier 1+2+3 kombiniert)
AI_LIBS = {
    # Tier 1
    "scikit-learn", "torch", "tensorflow", "torchvision", "nltk",
    "spacy", "keras", "torchaudio", "mxnet", "theano",
    "paddlepaddle", "tflearn", "dm-sonnet", "tensorflow-gpu", "tensorflow-cpu",
    # Tier 2
    "transformers", "openai", "langchain", "datasets", "sentence-transformers",
    "huggingface-hub", "accelerate", "llama-index-core", "peft", "diffusers",
    "tokenizers", "trl", "langchain-core", "langchain-community",
    "llama-index", "llama-cpp-python", "haystack-ai", "litellm",
    "guidance", "dspy", "crewai", "pyautogen", "autogen",
    "autogen-agentchat", "smolagents", "pydantic-ai", "instructor",
    "anthropic", "google-generativeai", "mistralai", "cohere",
    # Tier 3
    "xgboost", "jax", "gensim", "pytorch-lightning", "wandb",
    "lightgbm", "catboost", "chromadb", "faiss-cpu", "flax",
    "mlflow", "optuna", "qdrant-client", "deepspeed", "timm",
    "bitsandbytes", "stable-baselines3", "pymilvus", "weaviate-client",
    "pinecone", "fastai", "torch-geometric", "imbalanced-learn",
    "unsloth", "bentoml", "evidently",
}


def ts():
    return datetime.now().strftime("%H:%M:%S")


def _draw_adoption_plot(adoption_by_year, pilot, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib as mpl
    mpl.rcParams["font.family"] = "DejaVu Sans"

    # ── Daten aufbereiten ────────────────────────────────────────────────────
    # Normalisiere: MongoDB gibt "_id" zurueck, gespeichertes JSON gibt "year"
    adoption_by_year = [
        {"year": d.get("year", d.get("_id")), "count": d["count"]}
        for d in adoption_by_year
    ]
    data = sorted(adoption_by_year, key=lambda x: x["year"] or 0)
    data = [d for d in data if d["year"] and 2010 <= d["year"] <= 2025]
    years  = [d["year"] for d in data]
    counts = [d["count"] for d in data]

    # Kumulativ
    cumsum = []
    running = 0
    for c in counts:
        running += c
        cumsum.append(running)

    # AI-native / AI-boosted aus Pilot
    n_native  = pilot.get("ai_native", 0)
    n_boosted = pilot.get("ai_boosted", 0)
    total_cl  = n_native + n_boosted
    pct_native  = 100 * n_native  / total_cl if total_cl else 0
    pct_boosted = 100 * n_boosted / total_cl if total_cl else 0

    # ── Figure: 2 Subplots nebeneinander ─────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.patch.set_facecolor("white")

    COLOR_BAR  = "#2471A3"
    COLOR_LINE = "#E74C3C"
    COLOR_ANNO = "#1A1A2E"

    # ── Linkes Panel: Balken + Kumulativlinie ────────────────────────────────
    ax1.set_facecolor("white")
    bars = ax1.bar(years, counts, color=COLOR_BAR, alpha=0.75, width=0.7, zorder=2)

    ax1_r = ax1.twinx()
    ax1_r.plot(years, cumsum, color=COLOR_LINE, linewidth=2.5, marker="o",
               markersize=4, zorder=3, label="Kumulativ")
    ax1_r.set_ylabel("Kumulativ (alle Jahre)", color=COLOR_LINE, fontsize=10)
    ax1_r.tick_params(axis="y", colors=COLOR_LINE)
    ax1_r.spines["right"].set_color(COLOR_LINE)

    # Annotationen fuer Wendepunkte
    annotations = {
        2017: ("scikit-learn\nweit verbreitet", "above"),
        2020: ("BERT / GPT-2\nHuggingFace", "above"),
        2022: ("ChatGPT\nNov. 2022", "above"),
        2023: ("LLM-Boom\nLangChain etc.", "above"),
    }
    for yr, (label, pos) in annotations.items():
        if yr in years:
            idx = years.index(yr)
            yval = counts[idx]
            ax1.annotate(
                label,
                xy=(yr, yval),
                xytext=(yr, yval + max(counts) * 0.10),
                fontsize=7.5, ha="center", color=COLOR_ANNO,
                arrowprops=dict(arrowstyle="-", color="#AAAAAA", lw=0.8),
                bbox=dict(boxstyle="round,pad=0.2", fc="#F4F6FA", ec="#CCCCCC", lw=0.6)
            )

    ax1.set_xlabel("Jahr", fontsize=11)
    ax1.set_ylabel("Neue KI-Packages (erste KI-Dep)", fontsize=11)
    ax1.set_title("KI-Adoption im PyPI-Oekosystem\n(erste Version mit KI-Abhaengigkeit pro Jahr)",
                  fontsize=12, fontweight="bold", color=COLOR_ANNO, pad=12)
    ax1.set_xticks(years)
    ax1.set_xticklabels(years, rotation=45, ha="right", fontsize=9)
    ax1.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)
    ax1.spines[["top", "right"]].set_visible(False)

    # Legende
    patch_bar  = mpatches.Patch(color=COLOR_BAR,  alpha=0.75, label="Neue KI-Packages (Jahr)")
    patch_line = mpatches.Patch(color=COLOR_LINE, label="Kumulativ")
    ax1.legend(handles=[patch_bar, patch_line], loc="upper left", fontsize=9,
               framealpha=0.85)

    # ── Rechtes Panel: AI-native vs. AI-boosted Donut ────────────────────────
    ax2.set_facecolor("white")
    ax2.set_aspect("equal")

    COLOR_NATIVE  = "#1E8449"
    COLOR_BOOSTED = "#E67E22"
    COLOR_SKIP    = "#BDC3C7"

    n_skip = pilot.get("missing_timestamps", 0)
    sizes  = [n_native, n_boosted, n_skip]
    colors = [COLOR_NATIVE, COLOR_BOOSTED, COLOR_SKIP]
    labels_pie = [
        f"AI-native\n{n_native:,}  ({pct_native:.1f}%)",
        f"AI-boosted\n{n_boosted:,}  ({pct_boosted:.1f}%)",
        f"Kein Timestamp\n{n_skip:,}  (skip)",
    ]

    wedges, _ = ax2.pie(
        sizes, colors=colors, startangle=90,
        wedgeprops=dict(width=0.52, edgecolor="white", linewidth=2),
    )

    # Zentrum-Text
    ax2.text(0, 0.08, f"{total_cl:,}", fontsize=22, fontweight="bold",
             ha="center", va="center", color=COLOR_ANNO)
    ax2.text(0, -0.22, "klassifiziert\n(Pilot-Sample)", fontsize=9,
             ha="center", va="center", color="#555555")

    # Legende rechts
    legend_patches = [
        mpatches.Patch(color=COLOR_NATIVE,  label=f"AI-native — bereits 1. Version KI  ({pct_native:.1f}%)"),
        mpatches.Patch(color=COLOR_BOOSTED, label=f"AI-boosted — KI spaeter hinzugefuegt  ({pct_boosted:.1f}%)"),
        mpatches.Patch(color=COLOR_SKIP,    label=f"Kein Timestamp (uebersprungen)"),
    ]
    ax2.legend(handles=legend_patches, loc="lower center",
               bbox_to_anchor=(0.5, -0.22), fontsize=9.5,
               framealpha=0.9, edgecolor="#CCCCCC")

    ax2.set_title("AI-native vs. AI-boosted\n(Pilot: 1.000 KI-Packages aus Signal B)",
                  fontsize=12, fontweight="bold", color=COLOR_ANNO, pad=12)

    # Aussage-Box unter dem Donut
    insight = (
        f"Befund: {pct_native:.0f}% der KI-Packages wurden von Grund auf als KI-Projekt "
        f"gestartet (AI-native).\n"
        f"Nur {pct_boosted:.0f}% haben KI nachtraeglich als Abhaengigkeit hinzugefuegt (AI-boosted).\n"
        f"-> Grossteil des PyPI-KI-Oekosystems ist durch Neuentwicklung entstanden, nicht durch Umbau."
    )
    fig.text(0.52, 0.01, insight, fontsize=9, ha="center", va="bottom",
             color="#333333", style="italic",
             bbox=dict(boxstyle="round,pad=0.5", fc="#F9F9F9", ec="#CCCCCC", lw=0.8))

    plt.tight_layout(rect=[0, 0.07, 1, 1])

    out = Path(out_dir) / "viz_09_ai_native_boosted.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Plot gespeichert: {out.name}")


def _draw_timeline_plot(native_by_year, boosted_by_year, lag_by_year, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import matplotlib as mpl
    mpl.rcParams["font.family"] = "DejaVu Sans"

    all_years = sorted(set(native_by_year) | set(boosted_by_year))
    native_vals  = [native_by_year.get(y, 0) for y in all_years]
    boosted_vals = [boosted_by_year.get(y, 0) for y in all_years]
    lag_vals     = [lag_by_year.get(y) for y in all_years]

    COLOR_NATIVE  = "#1E8449"
    COLOR_BOOSTED = "#E67E22"
    COLOR_LAG     = "#8E44AD"
    COLOR_ANNO    = "#1A1A2E"

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10),
                                    gridspec_kw={"height_ratios": [3, 1.4]})
    fig.patch.set_facecolor("white")

    # ── Oberes Panel: gestapelte Balken native + boosted ─────────────────────
    ax1.set_facecolor("white")
    width = 0.62
    xs = range(len(all_years))

    bars_n = ax1.bar(xs, native_vals,  width, label="AI-native",  color=COLOR_NATIVE,  alpha=0.85, zorder=2)
    bars_b = ax1.bar(xs, boosted_vals, width, label="AI-boosted", color=COLOR_BOOSTED, alpha=0.85,
                     bottom=native_vals, zorder=2)

    # Kumulativlinien
    ax1_r = ax1.twinx()
    cum_native  = []
    cum_boosted = []
    rn = rb = 0
    for n, b in zip(native_vals, boosted_vals):
        rn += n; rb += b
        cum_native.append(rn)
        cum_boosted.append(rb)

    ax1_r.plot(xs, cum_native,  color=COLOR_NATIVE,  linestyle="--", linewidth=1.8,
               marker="o", markersize=3.5, alpha=0.7, label="Kumulativ native")
    ax1_r.plot(xs, cum_boosted, color=COLOR_BOOSTED, linestyle="--", linewidth=1.8,
               marker="s", markersize=3.5, alpha=0.7, label="Kumulativ boosted")
    ax1_r.set_ylabel("Kumulativ", fontsize=10, color="#555555")
    ax1_r.tick_params(axis="y", colors="#555555", labelsize=8)
    ax1_r.spines["right"].set_color("#CCCCCC")

    # Ereignis-Annotationen
    events = {
        2017: "PyTorch 1.0\nscikit-learn weit verbreitet",
        2020: "GPT-3 / HuggingFace\nTransformers",
        2022: "ChatGPT\nNov. 2022",
        2023: "LLM-Boom\nLangChain / LlamaIndex",
    }
    max_y = max(n + b for n, b in zip(native_vals, boosted_vals)) if native_vals else 1
    for yr, label in events.items():
        if yr in all_years:
            xi = all_years.index(yr)
            yv = native_vals[xi] + boosted_vals[xi]
            ax1.annotate(
                label,
                xy=(xi, yv), xytext=(xi, yv + max_y * 0.13),
                fontsize=7.5, ha="center", color=COLOR_ANNO,
                arrowprops=dict(arrowstyle="-", color="#AAAAAA", lw=0.8),
                bbox=dict(boxstyle="round,pad=0.25", fc="#FEFEFE", ec="#CCCCCC", lw=0.7),
                zorder=5
            )

    ax1.set_xticks(list(xs))
    ax1.set_xticklabels(all_years, rotation=45, ha="right", fontsize=9)
    ax1.set_ylabel("Neue KI-Packages pro Jahr", fontsize=11)
    ax1.set_title(
        "AI-native vs. AI-boosted — zeitliche Verteilung im PyPI-Oekosystem\n"
        "Balken: neue Packages pro Jahr  |  Gestrichelt: kumulativer Bestand",
        fontsize=12, fontweight="bold", color=COLOR_ANNO, pad=12
    )
    ax1.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
    ax1.spines[["top", "right"]].set_visible(False)

    # Legende kombiniert
    from matplotlib.lines import Line2D
    handles = [
        mpl.patches.Patch(color=COLOR_NATIVE,  alpha=0.85, label="AI-native (Geburt als KI-Projekt)"),
        mpl.patches.Patch(color=COLOR_BOOSTED, alpha=0.85, label="AI-boosted (KI nachtraeglich adoptiert)"),
        Line2D([0], [0], color=COLOR_NATIVE,  linestyle="--", linewidth=1.8, label="Kumulativ native"),
        Line2D([0], [0], color=COLOR_BOOSTED, linestyle="--", linewidth=1.8, label="Kumulativ boosted"),
    ]
    ax1.legend(handles=handles, loc="upper left", fontsize=9, framealpha=0.9)

    # ── Unteres Panel: Durchschnittlicher Lag (Monate) fuer AI-boosted ───────
    ax2.set_facecolor("white")

    lag_xs   = [all_years.index(y) for y in all_years if lag_vals[all_years.index(y)] is not None]
    lag_ys   = [v for v in lag_vals if v is not None]

    if lag_xs:
        ax2.fill_between(lag_xs, lag_ys, alpha=0.25, color=COLOR_LAG)
        ax2.plot(lag_xs, lag_ys, color=COLOR_LAG, linewidth=2.2, marker="o", markersize=4.5, zorder=3)

        # Annotation: Peak
        peak_i = lag_ys.index(max(lag_ys))
        ax2.annotate(
            f"Peak: {max(lag_ys):.0f} Monate\n(Pakete brauchten am laengsten)",
            xy=(lag_xs[peak_i], lag_ys[peak_i]),
            xytext=(lag_xs[peak_i], lag_ys[peak_i] + max(lag_ys) * 0.15),
            fontsize=7.5, ha="center", color=COLOR_LAG,
            arrowprops=dict(arrowstyle="-", color="#AAAAAA", lw=0.8),
            bbox=dict(boxstyle="round,pad=0.25", fc="#FEFEFE", ec="#CCCCCC", lw=0.7)
        )

        # Annotation: Trend-Pfeil
        if len(lag_ys) >= 4:
            trend = "steigt" if lag_ys[-1] > lag_ys[len(lag_ys)//2] else "sinkt"
            ax2.text(lag_xs[-1] - 0.5, lag_ys[-1] + max(lag_ys)*0.05,
                     f"Trend: {trend}",
                     fontsize=8, color=COLOR_LAG, ha="right")

    ax2.set_xticks(list(xs))
    ax2.set_xticklabels(all_years, rotation=45, ha="right", fontsize=9)
    ax2.set_ylabel("Ø Monate bis KI-Adoption\n(nur AI-boosted)", fontsize=9.5)
    ax2.set_title(
        "Wie lange warteten AI-boosted Packages bis zur ersten KI-Abhaengigkeit?",
        fontsize=10.5, fontweight="bold", color=COLOR_ANNO, pad=8
    )
    ax2.grid(axis="y", linestyle="--", alpha=0.35)
    ax2.spines[["top", "right"]].set_visible(False)

    # Erklaerungstext
    insight = (
        "Lesehilfe: Das obere Panel zeigt wie viele neue Packages in einem Jahr erstmals "
        "eine KI-Abhaengigkeit aufwiesen — aufgeteilt in AI-native (von Anfang an KI) "
        "und AI-boosted (KI nachtraeglich hinzugefuegt).\n"
        "Das untere Panel zeigt die durchschnittliche Wartezeit der AI-boosted Packages: "
        "ein sinkender Wert bedeutet, Packages adoptieren KI immer schneller nach ihrer Gruendung."
    )
    fig.text(0.5, -0.01, insight, fontsize=8.5, ha="center", va="bottom",
             color="#444444", style="italic",
             bbox=dict(boxstyle="round,pad=0.5", fc="#F9F9F9", ec="#CCCCCC", lw=0.7))

    plt.tight_layout(rect=[0, 0.07, 1, 1])

    out = Path(out_dir) / "viz_10_native_boosted_timeline.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Plot gespeichert: {out.name}")


def main():
    print(f"[{ts()}] Verbinde mit MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]
    db.command("ping")
    print(f"[{ts()}] Verbunden.\n")

    deps = db["depsPackagesDependencies"]
    results = {}

    # ── Block 1: Grundzahlen ─────────────────────────────────────────────────
    print(f"[{ts()}] Block 1: Grundzahlen...")

    n_total = deps.count_documents({})
    print(f"  Eintraege gesamt:          {n_total:>10,}")
    results["n_total_entries"] = n_total

    # Distinct package names
    t0 = time.time()
    n_distinct_names = len(deps.distinct("_id.name"))
    print(f"  Distinct Packages:         {n_distinct_names:>10,}  ({time.time()-t0:.1f}s)")
    results["n_distinct_packages"] = n_distinct_names

    # ── Block 2: uploadedAt Befuellung ───────────────────────────────────────
    print(f"\n[{ts()}] Block 2: uploadedAt Befuellung...")

    n_with_uploaded_at = deps.count_documents({"createdAt": {"$exists": True}})
    n_with_value = deps.count_documents({"createdAt": {"$exists": True, "$ne": None}})
    pct = 100 * n_with_value / n_total if n_total > 0 else 0
    print(f"  createdAt exists:          {n_with_uploaded_at:>10,}")
    print(f"  createdAt nicht null:      {n_with_value:>10,}  ({pct:.1f}%)")
    results["n_with_createdAt"] = n_with_value
    results["pct_with_createdAt"] = round(pct, 2)

    # Beispiel-Wert
    sample_doc = deps.find_one({"createdAt": {"$exists": True, "$ne": None}})
    if sample_doc:
        print(f"  Beispiel createdAt Typ:    {type(sample_doc['createdAt']).__name__}  Wert: {sample_doc['createdAt']}")
        results["createdAt_example_type"] = type(sample_doc["createdAt"]).__name__
        results["createdAt_example_value"] = str(sample_doc["createdAt"])

    # ── Block 3: Versionen pro Package ──────────────────────────────────────
    print(f"\n[{ts()}] Block 3: Versionen-Verteilung...")

    t0 = time.time()
    version_dist = list(deps.aggregate([
        {"$group": {"_id": "$_id.name", "n_versions": {"$sum": 1}}},
        {"$bucket": {
            "groupBy": "$n_versions",
            "boundaries": [1, 2, 3, 5, 10, 25, 50, 100],
            "default": "100+",
            "output": {"count": {"$sum": 1}}
        }}
    ], allowDiskUse=True))
    print(f"  ({time.time()-t0:.1f}s)")
    print(f"\n  Versionen pro Package:")
    total_pkgs = sum(d["count"] for d in version_dist)
    for d in version_dist:
        bar = "█" * min(40, int(40 * d["count"] / total_pkgs))
        print(f"    {str(d['_id']):>5} Versionen: {d['count']:>8,}  {bar}")
    results["versions_per_package_distribution"] = [
        {"bucket": str(d["_id"]), "count": d["count"]} for d in version_dist
    ]

    n_single_version = next((d["count"] for d in version_dist if d["_id"] == 1), 0)
    n_multi_version = total_pkgs - n_single_version
    print(f"\n  Nur 1 Version:             {n_single_version:>8,}  ({100*n_single_version/total_pkgs:.1f}%)")
    print(f"  Mehrere Versionen:         {n_multi_version:>8,}  ({100*n_multi_version/total_pkgs:.1f}%)")
    results["n_single_version_packages"] = n_single_version
    results["n_multi_version_packages"] = n_multi_version

    # ── Block 4: Beispiel — transformers alle Versionen ─────────────────────
    print(f"\n[{ts()}] Block 4: Beispiel 'transformers' alle Versionen...")

    example_versions = list(deps.find(
        {"_id.name": "transformers"},
        {"_id": 1, "createdAt": 1, "dependencies": 1}
    ).sort("createdAt", 1).limit(30))

    if example_versions:
        print(f"  Versionen gefunden: {len(example_versions)}")
        print(f"  {'Version':<20} {'createdAt':<25} {'KI-Deps (depth=1)'}")
        print(f"  {'─'*20} {'─'*25} {'─'*30}")
        for doc in example_versions[:15]:
            ver = doc["_id"].get("version", "?")
            uat = str(doc.get("createdAt", "—"))
            ki_deps = [
                d["name"] for d in doc.get("dependencies", [])
                if d.get("depth") == 1 and d.get("name", "").lower() in AI_LIBS
            ]
            print(f"  {ver:<20} {uat:<25} {', '.join(ki_deps[:3]) or '—'}")
        results["transformers_example_versions"] = len(example_versions)
    else:
        print(f"  'transformers' nicht gefunden in depsPackagesDependencies")
        results["transformers_example_versions"] = 0

    # ── Block 5: Pilot AI-native vs. AI-boosted ──────────────────────────────
    print(f"\n[{ts()}] Block 5: Pilot AI-native vs. AI-boosted (1000 KI-Packages)...")
    print(f"  (Nimmt 1000 Packages die mind. eine KI-Dep haben und klassifiziert sie)")

    # Finde 1000 Packages mit mindestens einer KI-Dep (depth=1)
    t0 = time.time()
    ki_pkg_sample = list(deps.aggregate([
        {"$match": {
            "dependencies": {
                "$elemMatch": {
                    "name": {"$in": list(AI_LIBS)},
                    "depth": 1
                }
            }
        }},
        {"$group": {"_id": "$_id.name"}},
        {"$limit": 1000}
    ], allowDiskUse=True))
    ki_pkg_names = [d["_id"] for d in ki_pkg_sample]
    print(f"  {len(ki_pkg_names)} KI-Packages fuer Pilot gesammelt  ({time.time()-t0:.1f}s)")

    ai_native = 0
    ai_boosted = 0
    only_one_version = 0
    missing_timestamps = 0

    for pkg_name in ki_pkg_names:
        all_versions = list(deps.find(
            {"_id.name": pkg_name},
            {"_id": 1, "createdAt": 1, "dependencies": 1}
        ))

        # Filter: nur Versionen mit createdAt
        versioned = [v for v in all_versions if v.get("createdAt")]

        if not versioned:
            missing_timestamps += 1
            continue

        # Sortiere nach createdAt
        versioned.sort(key=lambda x: x["createdAt"])

        # Erste Version overall
        first_version = versioned[0]

        # Erste Version MIT KI-Dep
        first_ki_version = None
        for v in versioned:
            ki_deps = [
                d for d in v.get("dependencies", [])
                if d.get("depth") == 1 and d.get("name", "").lower() in AI_LIBS
            ]
            if ki_deps:
                first_ki_version = v
                break

        if first_ki_version is None:
            # Keine KI-Dep gefunden (Timestamp-Filter hat KI-Versionen entfernt)
            missing_timestamps += 1
            continue

        if len(versioned) == 1:
            only_one_version += 1
            ai_native += 1  # Nur eine Version mit KI-Dep = native
        elif first_ki_version["_id"]["version"] == first_version["_id"]["version"]:
            ai_native += 1
        else:
            ai_boosted += 1

    classified = ai_native + ai_boosted
    print(f"\n  Klassifikations-Ergebnis ({len(ki_pkg_names)} KI-Packages):")
    print(f"  AI-native:                 {ai_native:>8,}  ({100*ai_native/len(ki_pkg_names):.1f}%)")
    print(f"  AI-boosted:                {ai_boosted:>8,}  ({100*ai_boosted/len(ki_pkg_names):.1f}%)")
    print(f"  Nur 1 Version (→native):   {only_one_version:>8,}")
    print(f"  Kein Timestamp (skip):     {missing_timestamps:>8,}  ({100*missing_timestamps/len(ki_pkg_names):.1f}%)")

    if classified > 0:
        print(f"\n  Unter den klassifizierbaren:")
        print(f"  AI-native:  {100*ai_native/classified:.1f}%")
        print(f"  AI-boosted: {100*ai_boosted/classified:.1f}%")

    results["pilot"] = {
        "sample_size": len(ki_pkg_names),
        "ai_native": ai_native,
        "ai_boosted": ai_boosted,
        "only_one_version": only_one_version,
        "missing_timestamps": missing_timestamps,
        "pct_native_of_classified": round(100 * ai_native / classified, 1) if classified > 0 else None,
        "pct_boosted_of_classified": round(100 * ai_boosted / classified, 1) if classified > 0 else None,
    }

    # ── Block 6: Zeitliche Verteilung der KI-Adoptionen ─────────────────────
    print(f"\n[{ts()}] Block 6: Jahr der ersten KI-Dep (alle KI-Packages via Signal B)...")

    t0 = time.time()
    adoption_by_year = list(deps.aggregate([
        # Nur Versionen mit KI-Dep und createdAt
        {"$match": {
            "createdAt": {"$exists": True, "$ne": None},
            "dependencies": {
                "$elemMatch": {
                    "name": {"$in": list(AI_LIBS)},
                    "depth": 1
                }
            }
        }},
        # Frueheste Version pro Package
        {"$sort": {"createdAt": 1}},
        {"$group": {
            "_id": "$_id.name",
            "first_ki_upload": {"$first": "$createdAt"}
        }},
        # Sekunden -> Millisekunden -> Date (onError: null fuer kaputte Werte)
        {"$addFields": {
            "first_ki_date": {"$convert": {
                "input": {"$multiply": ["$first_ki_upload", 1000]},
                "to": "date", "onError": None, "onNull": None
            }}
        }},
        {"$match": {"first_ki_date": {"$ne": None}}},
        {"$group": {
            "_id": {"$year": "$first_ki_date"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ], allowDiskUse=True))
    print(f"  ({time.time()-t0:.1f}s)")

    print(f"\n  Erste KI-Adoption pro Jahr:")
    for y in adoption_by_year:
        bar = "█" * min(50, y["count"] // 50)
        print(f"  {y['_id']}: {y['count']:>6,}  {bar}")

    results["adoption_by_year"] = [
        {"year": y["_id"], "count": y["count"]} for y in adoption_by_year
    ]

    # ── Block 7: AI-native vs. AI-boosted nach Jahr (volle Aggregation) ──────
    print(f"\n[{ts()}] Block 7: AI-native vs. AI-boosted nach Jahr (alle KI-Packages)...")
    print(f"  (Aggregiert alle Packages: Geburtsjahr vs. Jahr der KI-Adoption)")

    t0 = time.time()
    # Fuer jedes Package: frueheste Version (= Geburt) UND frueheste KI-Version
    timeline_raw = list(deps.aggregate([
        {"$match": {"createdAt": {"$exists": True, "$ne": None}}},
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
        # Frueheste Version mit KI
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
        # Nur Packages mit KI-Version
        {"$match": {"first_ki_created": {"$ne": None}}},
        # native = erste Version IST die KI-Version
        {"$addFields": {
            "is_native": {"$eq": ["$first_created", "$first_ki_created"]},
            "birth_year": {"$year": {"$convert": {"input": {"$multiply": ["$first_created", 1000]}, "to": "date", "onError": None, "onNull": None}}},
            "ki_year":    {"$year": {"$convert": {"input": {"$multiply": ["$first_ki_created", 1000]}, "to": "date", "onError": None, "onNull": None}}},
        }},
        # Nach Jahr + Typ gruppieren
        {"$group": {
            "_id": {
                "year": {"$cond": ["$is_native", "$birth_year", "$ki_year"]},
                "type": {"$cond": ["$is_native", "native", "boosted"]}
            },
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id.year": 1}}
    ], allowDiskUse=True))
    print(f"  ({time.time()-t0:.1f}s)")

    # Auch Lag-Zeit fuer AI-boosted (Median Monate zwischen Geburt und KI-Adoption)
    t0 = time.time()
    lag_raw = list(deps.aggregate([
        {"$match": {"createdAt": {"$exists": True, "$ne": None}}},
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
        {"$match": {
            "first_ki_created": {"$ne": None},
            "$expr": {"$gt": ["$first_ki_created", "$first_created"]},  # nur boosted
            # Ungueltige Timestamps herausfiltern: < 2008-01-01 (Unix: 1199145600)
            "first_created":    {"$gt": 1199145600},
            "first_ki_created": {"$gt": 1199145600},
        }},
        {"$addFields": {
            "lag_months": {"$divide": [
                {"$subtract": ["$first_ki_created", "$first_created"]},
                2592000  # Sekunden pro Monat
            ]},
            "ki_year": {"$year": {"$convert": {"input": {"$multiply": ["$first_ki_created", 1000]}, "to": "date", "onError": None, "onNull": None}}}
        }},
        {"$group": {
            "_id": "$ki_year",
            "median_lag_sum": {"$sum": "$lag_months"},
            "count": {"$sum": 1}
        }},
        {"$addFields": {"avg_lag_months": {"$divide": ["$median_lag_sum", "$count"]}}},
        {"$sort": {"_id": 1}}
    ], allowDiskUse=True))
    print(f"  Lag-Aggregation: ({time.time()-t0:.1f}s)")

    # Ausgabe
    native_by_year  = {}
    boosted_by_year = {}
    for d in timeline_raw:
        yr = d["_id"]["year"]
        typ = d["_id"]["type"]
        if yr and 2010 <= yr <= 2025:
            if typ == "native":
                native_by_year[yr] = d["count"]
            else:
                boosted_by_year[yr] = d["count"]

    lag_by_year = {
        d["_id"]: round(d["avg_lag_months"], 1)
        for d in lag_raw
        if d["_id"] and 2010 <= d["_id"] <= 2025
    }

    all_years = sorted(set(native_by_year) | set(boosted_by_year))
    print(f"\n  {'Jahr':>6}  {'Native':>8}  {'Boosted':>8}  {'Lag (Monate Ø)':>15}")
    print(f"  {'─'*6}  {'─'*8}  {'─'*8}  {'─'*15}")
    for yr in all_years:
        n = native_by_year.get(yr, 0)
        b = boosted_by_year.get(yr, 0)
        lag = lag_by_year.get(yr, "—")
        print(f"  {yr:>6}  {n:>8,}  {b:>8,}  {str(lag):>15}")

    results["native_boosted_by_year"] = [
        {"year": yr,
         "native": native_by_year.get(yr, 0),
         "boosted": boosted_by_year.get(yr, 0),
         "avg_lag_months": lag_by_year.get(yr)}
        for yr in all_years
    ]

    # ── Plots ────────────────────────────────────────────────────────────────
    print(f"\n[{ts()}] Erstelle Plots...")
    _draw_adoption_plot(adoption_by_year, results["pilot"], OUT_JSON.parent)
    _draw_timeline_plot(native_by_year, boosted_by_year, lag_by_year, OUT_JSON.parent)

    # ── Speichern ────────────────────────────────────────────────────────────
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Ergebnisse: {OUT_JSON}")

    client.close()
    print(f"\n[{ts()}] Fertig.")


if __name__ == "__main__":
    import sys
    if "--plots-only" in sys.argv:
        # Liest gespeicherte JSON und generiert nur Plots neu — kein MongoDB
        if not OUT_JSON.exists():
            print(f"Fehler: {OUT_JSON} nicht gefunden. Erst ohne --plots-only ausfuehren.")
            sys.exit(1)
        with open(OUT_JSON, encoding="utf-8") as f:
            saved = json.load(f)

        adoption_raw = saved.get("adoption_by_year", [])
        pilot        = saved.get("pilot", {})
        nb_raw       = saved.get("native_boosted_by_year", [])

        native_by_year  = {d["year"]: d["native"]  for d in nb_raw if d.get("year")}
        boosted_by_year = {d["year"]: d["boosted"] for d in nb_raw if d.get("year")}
        lag_by_year     = {d["year"]: d["avg_lag_months"] for d in nb_raw
                           if d.get("year") and d.get("avg_lag_months") is not None}

        print("=== Plots-only Modus ===")
        _draw_adoption_plot(adoption_raw, pilot, OUT_JSON.parent)
        _draw_timeline_plot(native_by_year, boosted_by_year, lag_by_year, OUT_JSON.parent)
        print("=== Fertig ===")
    else:
        main()
