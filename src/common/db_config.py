"""
db_config.py — Zentrale MongoDB-Verbindungskonfiguration ueber CLI-Flags.

Verwendung in jedem Analyse-Skript:
    from common.db_config import get_mongo_uri
    MONGO_URI = get_mongo_uri()

Aufruf-Varianten:
    python script.py --mongo-uri "mongodb://user:pass@host:27017/db?replicaSet=rs0"
    python script.py --mongo-host host:27017 --mongo-user USER --mongo-pass PASS --mongo-db DBNAME
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
        help="Vollstaendiger MongoDB-Connection-String (ueberschreibt alle anderen Mongo-Flags).")
    parser.add_argument("--mongo-host", type=str, default=None,
        help="MongoDB Host inkl. Port, z.B. host.example.com:27017")
    parser.add_argument("--mongo-user", type=str, default=None,
        help="MongoDB Benutzername")
    parser.add_argument("--mongo-pass", type=str, default=None,
        help="MongoDB Passwort")
    parser.add_argument("--mongo-db", type=str, default="upstreamPackages",
        help="MongoDB Datenbankname (Default: upstreamPackages)")
    parser.add_argument("--mongo-replica-set", type=str, default="rs0",
        help="Replica-Set-Name (Default: rs0)")
    return parser


def get_mongo_uri(argv=None):
    parser = _build_parser()
    args, _ = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    if args.mongo_uri:
        return args.mongo_uri

    if args.mongo_host and args.mongo_user and args.mongo_pass:
        return (
            f"mongodb://{args.mongo_user}:{args.mongo_pass}@{args.mongo_host}/"
            f"{args.mongo_db}?replicaSet={args.mongo_replica_set}"
        )

    env_uri = os.getenv("MONGO_URI")
    if env_uri:
        return env_uri

    parser.error(
        "Keine MongoDB-Zugangsdaten gefunden. Nutze:\n"
        "  --mongo-uri 'mongodb://user:pass@host:27017/db?replicaSet=rs0'\n"
        "oder:\n"
        "  --mongo-host HOST:PORT --mongo-user USER --mongo-pass PASS\n"
        "oder setze die Umgebungsvariable MONGO_URI."
    )


def add_mongo_args(parser):
    return _build_parser(existing_parser=parser)
