"""
paths.py — Zentrale Pfad-Konfiguration fuer alle Analyse-Skripte.

Stellt sicher, dass ALLE Outputs (Plots, CSVs, Logs) unabhaengig davon,
von wo ein Skript gestartet wird, im selben zentralen Outputs/-Ordner
im Repo-Root landen.

Verwendung in jedem Analyse-Skript:
    from common.paths import get_output_dir
    OUT_DIR = get_output_dir()
"""

import os


def get_repo_root():
    """
    Ermittelt den Repo-Root robust ueber os.path, ausgehend von der
    Position dieser Datei (src/common/paths.py -> zwei Ebenen nach oben).
    """
    this_file = os.path.abspath(__file__)
    common_dir = os.path.dirname(this_file)
    src_dir = os.path.dirname(common_dir)
    repo_root = os.path.dirname(src_dir)
    return repo_root


def get_output_dir(subfolder=None):
    """
    Gibt den zentralen Outputs/-Ordner zurueck (im Repo-Root) und legt ihn
    bei Bedarf an. Optional kann ein Unterordner (z.B. 'figures', 'tables')
    angegeben werden.
    """
    root = get_repo_root()
    out_dir = os.path.join(root, "Outputs")
    if subfolder:
        out_dir = os.path.join(out_dir, subfolder)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def get_data_dir(subfolder=None):
    """Analog zu get_output_dir, aber fuer den data/-Ordner (Input-Daten)."""
    root = get_repo_root()
    data_dir = os.path.join(root, "data")
    if subfolder:
        data_dir = os.path.join(data_dir, subfolder)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir
