"""
run_all.py — Alle Analyse-Skripte sequenziell ausfuehren

Reihenfolge:
  1. build_ki_repo_mapping.py     KI-Klassifikation -> ki_repo_mapping.json
  2. build_repo_features.py       repo_features.csv bauen
  3. count_signals.py             Signal A/B zaehlen + Kennzahlen 5/7
  4. panel_analysis.py            Commit/Contributor-Wachstum (Panel)
  5. descriptive_stats.py         Stars/Lizenz/Org Querschnitt
  6. viz_activity_analysis.py     Aktivitaets-Plots (alle Gruppen)
  7. event_study.py               Event Study AI-Adoption t=0
  8. analyze_repo_features.py     OLS HC3 + Clustered SE + Stars-Plot

Aufruf:
  python run_all.py [--mongo-uri "..."] [--mongo-db upstreamPackages]
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import sys as _sys
import argparse as _argparse
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from common.paths import get_output_dir

_p = _argparse.ArgumentParser(add_help=False)
_p.add_argument("--mongo-db", default="upstreamPackages")
_args, _extra = _p.parse_known_args()

SRC_DIR  = Path(__file__).resolve().parent
OUT_DIR  = Path(get_output_dir())
LOG_FILE = OUT_DIR / "run_all_log.txt"

SCRIPTS = [
    ("01_data_pipeline/build_ki_repo_mapping.py",  "KI-Klassifikation -> ki_repo_mapping.json"),
    ("01_data_pipeline/build_repo_features.py",    "repo_features.csv bauen"),
    ("02_signal_analysis/count_signals.py",        "Signal A/B zaehlen + Kennzahlen 5/7"),
    ("03_descriptive/panel_analysis.py",           "Commit/Contributor-Wachstum (Panel)"),
    ("03_descriptive/descriptive_stats.py",        "Stars/Lizenz/Org Querschnitt"),
    ("03_descriptive/viz_activity_analysis.py",    "Aktivitaets-Plots (alle Gruppen inkl. Non-AI)"),
    ("04_event_study/event_study.py",              "Event Study: AI-Adoption Monat t=0"),
    ("05_regression/analyze_repo_features.py",     "OLS HC3 + Clustered SE + Stars-Plot"),
]

MONGO_ARGS = _extra


def ts():
    return datetime.now().strftime("%H:%M:%S")


def run_script(rel_path, desc, log):
    path = SRC_DIR / rel_path
    name = Path(rel_path).name
    print(f"\n[{ts()}] {'='*60}")
    print(f"[{ts()}] START: {name}")
    print(f"          {desc}")
    log.write(f"\n{'='*60}\n[{ts()}] START: {name}\n{desc}\n")

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(path)] + MONGO_ARGS,
        cwd=str(SRC_DIR),
        capture_output=True,
        text=True
    )
    elapsed = time.time() - t0

    if result.stdout:
        print(result.stdout)
        log.write(result.stdout)
    if result.stderr:
        print(f"[STDERR]:\n{result.stderr}")
        log.write(f"[STDERR]:\n{result.stderr}")

    status = "OK" if result.returncode == 0 else f"FEHLER (code={result.returncode})"
    print(f"[{ts()}] {status}  ({elapsed:.1f}s)")
    log.write(f"[{ts()}] {status}  ({elapsed:.1f}s)\n")
    return result.returncode == 0


def main():
    print(f"run_all.py gestartet: {datetime.now().isoformat(timespec='seconds')}")
    print(f"Output: {OUT_DIR}")
    print(f"Log:    {LOG_FILE}")

    with open(LOG_FILE, "w", encoding="utf-8") as log:
        log.write(f"run_all.py — {datetime.now().isoformat()}\n")
        log.write(f"Output: {OUT_DIR}\n")

        results = []
        for rel_path, desc in SCRIPTS:
            ok = run_script(rel_path, desc, log)
            results.append((Path(rel_path).name, ok))

        print(f"\n\n{'='*60}")
        print("ZUSAMMENFASSUNG")
        log.write(f"\n{'='*60}\nZUSAMMENFASSUNG\n")
        all_ok = True
        for name, ok in results:
            status = "OK" if ok else "FEHLER"
            print(f"  {'✓' if ok else '✗'}  {status}  {name}")
            log.write(f"  {'OK' if ok else 'FEHLER'}  {name}\n")
            if not ok:
                all_ok = False

        print(f"\nFertig: {datetime.now().isoformat(timespec='seconds')}")
        log.write(f"\nFertig: {datetime.now().isoformat()}\n")
        if not all_ok:
            print("\nACHTUNG: Mindestens ein Skript hat Fehler. Log pruefen.")


if __name__ == "__main__":
    main()
