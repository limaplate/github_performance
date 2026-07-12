"""
db_config.py — Zentrale MongoDB-Verbindungskonfiguration ueber CLI-Flags.

Die Working-Datenbank ist in jedem Skript als DB_NAME = "upstreamPackagesV2"
hardcodiert. Diese Datei liefert nur die Verbindungs-URI (Credentials + Host).

Aufruf-Varianten:
    python script.py --mongo-uri "mongodb://user:pass@host:27017/upstreamPackages?replicaSet=rs0"
    export MONGO_URI="mongodb://..."   # Alternative ohne Flags
    python script.py
"""

import argparse
import os
import sys


def _build_parser(existing_parser=None):
    parser = existing_parser or argparse.ArgumentParser(
        description="MongoDB-Verbindung fuer Analyse-Skripte",
        add_help=False,
    )
    parser.add_argument("--mongo-uri", type=str, default=None,
        help="Vollstaendiger MongoDB-Connection-String.")
    return parser


def get_mongo_uri(argv=None):
    parser = _build_parser()
    args, _ = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    if args.mongo_uri:
        return args.mongo_uri

    env_uri = os.getenv("MONGO_URI")
    if env_uri:
        return env_uri

    parser.error(
        "Keine MongoDB-URI gefunden. Nutze:\n"
        "  --mongo-uri 'mongodb://user:pass@host:27017/upstreamPackages?replicaSet=rs0'\n"
        "oder setze die Umgebungsvariable MONGO_URI."
    )


def add_mongo_args(parser):
    return _build_parser(existing_parser=parser)
