"""
paths.py — Zentrale Pfad-Konfiguration fuer alle Analyse-Skripte.

Stellt sicher, dass ALLE Outputs (Plots, CSVs, Logs) unabhaengig davon,
von wo ein Skript gestartet wird, im selben zentralen outputs/-Ordner
im Repo-Root landen.

Verwendung in jedem Analyse-Skript:
    from common.paths import get_output_dir
    OUT_DIR = get_output_dir()
"""

from pathlib import Path


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_output_dir(subfolder=None) -> Path:
    out_dir = get_repo_root() / "outputs"
    if subfolder:
        out_dir = out_dir / subfolder
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def get_data_dir(subfolder=None) -> Path:
    data_dir = get_repo_root() / "data"
    if subfolder:
        data_dir = data_dir / subfolder
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
