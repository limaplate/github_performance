"""
draw_timeline_plots.py — Generiert viz_09 + viz_10 aus bekannten Ergebnissen.
Kein MongoDB noetig — Zahlen direkt aus dem letzten Run eingetragen.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import matplotlib as mpl
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.paths import get_output_dir

mpl.rcParams["font.family"] = "DejaVu Sans"
OUT_DIR = get_output_dir()
# ── Daten aus Block 6 ────────────────────────────────────────────────────────
ADOPTION_BY_YEAR = [
    {"year": 2013, "count": 2},
    {"year": 2014, "count": 6},
    {"year": 2015, "count": 23},
    {"year": 2016, "count": 80},
    {"year": 2017, "count": 274},
    {"year": 2018, "count": 726},
    {"year": 2019, "count": 1623},
    {"year": 2020, "count": 3091},
    {"year": 2021, "count": 3721},
    {"year": 2022, "count": 4446},
    {"year": 2023, "count": 8610},
    {"year": 2024, "count": 5742},
]

# ── Daten aus Block 7 ────────────────────────────────────────────────────────
NATIVE_BOOSTED = [
    {"year": 2013, "native":    1, "boosted":    1, "avg_lag": 534.5},
    {"year": 2014, "native":    1, "boosted":    5, "avg_lag": 329.0},
    {"year": 2015, "native":   12, "boosted":   11, "avg_lag": 357.4},
    {"year": 2016, "native":   42, "boosted":   38, "avg_lag": 228.5},
    {"year": 2017, "native":  170, "boosted":  104, "avg_lag": 253.4},
    {"year": 2018, "native":  438, "boosted":  288, "avg_lag": 207.9},
    {"year": 2019, "native": 1063, "boosted":  560, "avg_lag": 165.6},
    {"year": 2020, "native": 2107, "boosted":  984, "avg_lag": 158.3},
    {"year": 2021, "native": 2585, "boosted": 1136, "avg_lag": 154.0},
    {"year": 2022, "native": 3206, "boosted": 1240, "avg_lag": 111.3},
    {"year": 2023, "native": 6481, "boosted": 2129, "avg_lag":  63.4},
    {"year": 2024, "native": 4479, "boosted": 1263, "avg_lag":  39.3},
]

PILOT = {"ai_native": 756, "ai_boosted": 243, "missing_timestamps": 1}


# ── viz_09: Adoptionskurve + Donut ──────────────────────────────────────────

def draw_viz_09():
    data   = ADOPTION_BY_YEAR
    years  = [d["year"] for d in data]
    counts = [d["count"] for d in data]

    cumsum = []
    running = 0
    for c in counts:
        running += c
        cumsum.append(running)

    n_native  = PILOT["ai_native"]
    n_boosted = PILOT["ai_boosted"]
    n_skip    = PILOT["missing_timestamps"]
    total_cl  = n_native + n_boosted
    pct_n = 100 * n_native  / total_cl
    pct_b = 100 * n_boosted / total_cl

    COLOR_BAR  = "#2471A3"
    COLOR_LINE = "#E74C3C"
    COLOR_ANNO = "#1A1A2E"
    COLOR_NATIVE  = "#1E8449"
    COLOR_BOOSTED = "#E67E22"
    COLOR_SKIP    = "#BDC3C7"

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.patch.set_facecolor("white")

    # Linkes Panel: Balken + Kumulativ
    ax1.set_facecolor("white")
    ax1.bar(years, counts, color=COLOR_BAR, alpha=0.75, width=0.7, zorder=2)

    ax1_r = ax1.twinx()
    ax1_r.plot(years, cumsum, color=COLOR_LINE, linewidth=2.5,
               marker="o", markersize=4, zorder=3)
    ax1_r.set_ylabel("Kumulativ", color=COLOR_LINE, fontsize=10)
    ax1_r.tick_params(axis="y", colors=COLOR_LINE)
    ax1_r.spines["right"].set_color(COLOR_LINE)

    events = {
        2017: ("scikit-learn /\nPyTorch weit verbreitet", 274),
        2020: ("GPT-3 / HuggingFace\nTransformers", 3091),
        2022: ("ChatGPT\nNov. 2022", 4446),
        2023: ("LLM-Boom\nLangChain etc.", 8610),
    }
    for yr, (label, yv) in events.items():
        ax1.annotate(label, xy=(yr, yv),
                     xytext=(yr, yv + max(counts) * 0.11),
                     fontsize=7.5, ha="center", color=COLOR_ANNO,
                     arrowprops=dict(arrowstyle="-", color="#AAAAAA", lw=0.8),
                     bbox=dict(boxstyle="round,pad=0.2", fc="#F4F6FA", ec="#CCCCCC", lw=0.6))

    ax1.set_xlabel("Jahr", fontsize=11)
    ax1.set_ylabel("Neue KI-Packages (erste KI-Abhaengigkeit)", fontsize=11)
    ax1.set_title("KI-Adoption im PyPI-Oekosystem\n(Jahr der ersten KI-Abhaengigkeit pro Package)",
                  fontsize=12, fontweight="bold", color=COLOR_ANNO, pad=12)
    ax1.set_xticks(years)
    ax1.set_xticklabels(years, rotation=45, ha="right", fontsize=9)
    ax1.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)
    ax1.spines[["top", "right"]].set_visible(False)

    patch_bar  = mpatches.Patch(color=COLOR_BAR,  alpha=0.75, label="Neue KI-Packages (Jahr)")
    patch_line = mpatches.Patch(color=COLOR_LINE, label="Kumulativ")
    ax1.legend(handles=[patch_bar, patch_line], loc="upper left", fontsize=9, framealpha=0.85)

    # Rechtes Panel: Donut
    ax2.set_facecolor("white")
    ax2.set_aspect("equal")

    sizes  = [n_native, n_boosted, n_skip]
    colors = [COLOR_NATIVE, COLOR_BOOSTED, COLOR_SKIP]
    ax2.pie(sizes, colors=colors, startangle=90,
            wedgeprops=dict(width=0.52, edgecolor="white", linewidth=2))

    ax2.text(0, 0.08, f"{total_cl:,}", fontsize=22, fontweight="bold",
             ha="center", va="center", color=COLOR_ANNO)
    ax2.text(0, -0.22, "klassifiziert\n(Pilot-Sample)", fontsize=9,
             ha="center", va="center", color="#555555")

    legend_patches = [
        mpatches.Patch(color=COLOR_NATIVE,  label=f"AI-native  ({pct_n:.1f}%)  —  von Anfang an KI"),
        mpatches.Patch(color=COLOR_BOOSTED, label=f"AI-boosted  ({pct_b:.1f}%)  —  KI nachtraeglich"),
        mpatches.Patch(color=COLOR_SKIP,    label="Kein Timestamp (skip)"),
    ]
    ax2.legend(handles=legend_patches, loc="lower center",
               bbox_to_anchor=(0.5, -0.22), fontsize=9.5,
               framealpha=0.9, edgecolor="#CCCCCC")
    ax2.set_title("AI-native vs. AI-boosted\n(Pilot-Sample: 1.000 KI-Packages)",
                  fontsize=12, fontweight="bold", color=COLOR_ANNO, pad=12)

    insight = (
        f"Befund: {pct_n:.0f}% der KI-Packages wurden von Anfang an als KI-Projekt gestartet (AI-native). "
        f"Nur {pct_b:.0f}% haben KI nachtraeglich hinzugefuegt (AI-boosted).\n"
        f"Das KI-Oekosystem waechst vor allem durch Neuprojekte — nicht durch Umbau bestehender Pakete."
    )
    fig.text(0.5, 0.01, insight, fontsize=9, ha="center", va="bottom",
             color="#333333", style="italic",
             bbox=dict(boxstyle="round,pad=0.5", fc="#F9F9F9", ec="#CCCCCC", lw=0.8))

    plt.tight_layout(rect=[0, 0.09, 1, 1])
    out = OUT_DIR / "viz_09_ai_native_boosted.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Gespeichert: {out.name}")


# ── viz_10: Timeline native vs. boosted + Lag ────────────────────────────────

def draw_viz_10():
    data = NATIVE_BOOSTED
    years        = [d["year"]    for d in data]
    native_vals  = [d["native"]  for d in data]
    boosted_vals = [d["boosted"] for d in data]
    lag_vals     = [d["avg_lag"] for d in data]

    COLOR_NATIVE  = "#1E8449"
    COLOR_BOOSTED = "#E67E22"
    COLOR_LAG     = "#8E44AD"
    COLOR_ANNO    = "#1A1A2E"

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 11),
                                    gridspec_kw={"height_ratios": [3, 1.5]})
    fig.patch.set_facecolor("white")

    xs = list(range(len(years)))

    # ── Oberes Panel: gestapelte Balken ──────────────────────────────────────
    ax1.set_facecolor("white")
    ax1.bar(xs, native_vals,  0.62, label="AI-native",
            color=COLOR_NATIVE,  alpha=0.85, zorder=2)
    ax1.bar(xs, boosted_vals, 0.62, label="AI-boosted",
            color=COLOR_BOOSTED, alpha=0.85, bottom=native_vals, zorder=2)

    # Kumulativlinien
    ax1_r = ax1.twinx()
    cum_n, cum_b, rn, rb = [], [], 0, 0
    for n, b in zip(native_vals, boosted_vals):
        rn += n; rb += b
        cum_n.append(rn); cum_b.append(rb)

    ax1_r.plot(xs, cum_n, color=COLOR_NATIVE,  linestyle="--", linewidth=1.8,
               marker="o", markersize=3.5, alpha=0.7)
    ax1_r.plot(xs, cum_b, color=COLOR_BOOSTED, linestyle="--", linewidth=1.8,
               marker="s", markersize=3.5, alpha=0.7)
    ax1_r.set_ylabel("Kumulativ", fontsize=9, color="#555555")
    ax1_r.tick_params(axis="y", colors="#555555", labelsize=8)
    ax1_r.spines["right"].set_color("#CCCCCC")

    # Ereignis-Annotationen
    events = {
        2017: "PyTorch /\nscikit-learn",
        2020: "GPT-3 /\nHuggingFace",
        2022: "ChatGPT\nNov. 2022",
        2023: "LLM-Boom",
    }
    max_y = max(n + b for n, b in zip(native_vals, boosted_vals))
    for yr, label in events.items():
        if yr in years:
            xi = years.index(yr)
            yv = native_vals[xi] + boosted_vals[xi]
            ax1.annotate(label, xy=(xi, yv),
                         xytext=(xi, yv + max_y * 0.12),
                         fontsize=7.5, ha="center", color=COLOR_ANNO,
                         arrowprops=dict(arrowstyle="-", color="#AAAAAA", lw=0.8),
                         bbox=dict(boxstyle="round,pad=0.25", fc="#FEFEFE", ec="#CCCCCC", lw=0.7),
                         zorder=5)

    # Ratio-Label in jedem Balken
    for xi, (n, b) in enumerate(zip(native_vals, boosted_vals)):
        total = n + b
        if total > 100:
            pct = 100 * n / total
            ax1.text(xi, total + max_y * 0.01, f"{pct:.0f}%\nnative",
                     fontsize=6.5, ha="center", va="bottom", color=COLOR_NATIVE)

    ax1.set_xticks(xs)
    ax1.set_xticklabels(years, rotation=45, ha="right", fontsize=9)
    ax1.set_ylabel("Neue KI-Packages pro Jahr", fontsize=11)
    ax1.set_title(
        "AI-native vs. AI-boosted — Zeitliche Entwicklung im PyPI-Oekosystem\n"
        "Balken: neue Packages pro Jahr  |  Gestrichelt: kumulativer Bestand  |  % = Anteil AI-native",
        fontsize=12, fontweight="bold", color=COLOR_ANNO, pad=12
    )
    ax1.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
    ax1.spines[["top", "right"]].set_visible(False)

    handles = [
        mpatches.Patch(color=COLOR_NATIVE,  alpha=0.85, label="AI-native  (Geburt als KI-Projekt)"),
        mpatches.Patch(color=COLOR_BOOSTED, alpha=0.85, label="AI-boosted  (KI nachtraeglich adoptiert)"),
        mlines.Line2D([], [], color=COLOR_NATIVE,  linestyle="--", linewidth=1.8, label="Kumulativ native"),
        mlines.Line2D([], [], color=COLOR_BOOSTED, linestyle="--", linewidth=1.8, label="Kumulativ boosted"),
    ]
    ax1.legend(handles=handles, loc="upper left", fontsize=9, framealpha=0.9)

    # ── Unteres Panel: Lag-Zeit ──────────────────────────────────────────────
    ax2.set_facecolor("white")
    ax2.fill_between(xs, lag_vals, alpha=0.20, color=COLOR_LAG)
    ax2.plot(xs, lag_vals, color=COLOR_LAG, linewidth=2.4,
             marker="o", markersize=5, zorder=3)

    # Werte beschriften
    for xi, v in enumerate(lag_vals):
        ax2.text(xi, v + 8, f"{v:.0f}", fontsize=7.5, ha="center",
                 color=COLOR_LAG, fontweight="bold")

    # Peak und aktueller Wert
    peak_i = lag_vals.index(max(lag_vals))
    ax2.annotate(
        f"Peak: {lag_vals[peak_i]:.0f} Monate\n(~{lag_vals[peak_i]/12:.1f} Jahre Vorlauf)",
        xy=(xs[peak_i], lag_vals[peak_i]),
        xytext=(xs[peak_i] + 1.5, lag_vals[peak_i] - 40),
        fontsize=8, color=COLOR_LAG,
        arrowprops=dict(arrowstyle="->", color=COLOR_LAG, lw=1.2),
        bbox=dict(boxstyle="round,pad=0.3", fc="#F9F0FF", ec=COLOR_LAG, lw=0.8)
    )
    ax2.annotate(
        f"2024: {lag_vals[-1]:.0f} Monate\n(~{lag_vals[-1]/12:.1f} Jahre)",
        xy=(xs[-1], lag_vals[-1]),
        xytext=(xs[-1] - 2.5, lag_vals[-1] + 30),
        fontsize=8, color=COLOR_LAG,
        arrowprops=dict(arrowstyle="->", color=COLOR_LAG, lw=1.2),
        bbox=dict(boxstyle="round,pad=0.3", fc="#F9F0FF", ec=COLOR_LAG, lw=0.8)
    )

    ax2.set_xticks(xs)
    ax2.set_xticklabels(years, rotation=45, ha="right", fontsize=9)
    ax2.set_ylabel("Durchschnittlicher Lag\n(Monate bis KI-Adoption)", fontsize=9.5)
    ax2.set_title(
        "Wie lange dauerte es bis AI-boosted Packages ihre erste KI-Abhängigkeit hinzufügten?\n"
        "(Monate zwischen erster Package-Version und erster KI-Abhängigkeit, nur gültige Timestamps ≥ 2008)",
        fontsize=10.5, fontweight="bold", color=COLOR_ANNO, pad=8
    )
    ax2.grid(axis="y", linestyle="--", alpha=0.35)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.set_ylim(0, max(lag_vals) * 1.35)

    # Erklaerungsbox
    insight = (
        "Lesehilfe: Oben — wie viele neue Packages bekamen in diesem Jahr erstmals eine KI-Abhaengigkeit? "
        "Gruen = von Anfang an KI-Projekt (AI-native), Orange = KI wurde nachtraeglich hinzugefuegt (AI-boosted).\n"
        "Unten — wie viele Monate lagen zwischen Paket-Gruendung und erster KI-Dep (nur AI-boosted)? "
        "Der starke Rueckgang zeigt: Packages adoptieren KI immer schneller — der LLM-Boom beschleunigt die Adoption."
    )
    fig.text(0.5, -0.01, insight, fontsize=8.5, ha="center", va="bottom",
             color="#444444", style="italic",
             bbox=dict(boxstyle="round,pad=0.5", fc="#F9F9F9", ec="#CCCCCC", lw=0.7))

    plt.tight_layout(rect=[0, 0.08, 1, 1])
    out = OUT_DIR / "viz_10_native_boosted_timeline.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Gespeichert: {out.name}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Generiere Timeline-Plots ===")
    draw_viz_09()
    draw_viz_10()
    print("=== Fertig ===")
