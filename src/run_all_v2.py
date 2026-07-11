"""
run_all_v2.py — Alle Analyse-Skripte sequenziell ausfuehren

Reihenfolge:
  1. analyze_repo_features_v2.py  (Dedup + OLS HC3 + Clustered SE + viz_29)
  2. event_study.py               (Event Study AI-Boosted, neu)
  3. core_analysis.py             (Commit/Contributor-Wachstum, neu)
  4. viz_activity_analysis.py     (Aktivitaets-Plots Folien 21/23/25/27)
  5. viz_21_nonai_only.py         (Non-AI Aktivitaet fix)

Alle Outputs landen im selben Ordner.
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from common.paths import get_output_dir

OUT_DIR = get_output_dir()
LOG_FILE = OUT_DIR / "run_all_v2_log.txt"

SCRIPTS = [
    ("analyze_repo_features_v2.py",  "OLS + Clustered SE + Stars-Plot (kein MongoDB-Call noetig)"),
    ("event_study.py",                "Event Study: AI-Adoption Monat t=0"),
    ("core_analysis.py",              "Commit/Contributor-Wachstum"),
    ("viz_activity_analysis.py",      "Aktivitaets-Plots Folien 21/23/25/27"),
    ("viz_21_nonai_only.py",          "Non-AI Aktivitaet (exklusiv)"),
]


def ts():
    return datetime.now().strftime("%H:%M:%S")


def run_script(name, desc, log):
    path = OUT_DIR / name
    print(f"\n[{ts()}] {'='*60}")
    print(f"[{ts()}] START: {name}")
    print(f"          {desc}")
    log.write(f"\n{'='*60}\n[{ts()}] START: {name}\n{desc}\n")

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(OUT_DIR),
        capture_output=True,
        text=True
    )
    elapsed = time.time() - t0

    # Ausgabe
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
    print(f"run_all_v2.py gestartet: {datetime.now().isoformat(timespec='seconds')}")
    print(f"Ordner: {OUT_DIR}")
    print(f"Log:    {LOG_FILE}")

    with open(LOG_FILE, "w", encoding="utf-8") as log:
        log.write(f"run_all_v2.py — {datetime.now().isoformat()}\n")
        log.write(f"Ordner: {OUT_DIR}\n")

        results = []
        for name, desc in SCRIPTS:
            ok = run_script(name, desc, log)
            results.append((name, ok))

        print(f"\n\n{'='*60}")
        print(f"ZUSAMMENFASSUNG")
        log.write(f"\n{'='*60}\nZUSAMMENFASSUNG\n")
        all_ok = True
        for name, ok in results:
            status = "✓  OK" if ok else "✗  FEHLER"
            print(f"  {status}  {name}")
            log.write(f"  {'OK' if ok else 'FEHLER'}  {name}\n")
            if not ok:
                all_ok = False

        print(f"\nFertig: {datetime.now().isoformat(timespec='seconds')}")
        log.write(f"\nFertig: {datetime.now().isoformat()}\n")
        if all_ok:
            print("Alle Skripte erfolgreich.")
        else:
            print("\nACHTUNG: Mindestens ein Skript hat Fehler geworfen. Log pruefen.")


if __name__ == "__main__":
    main()
