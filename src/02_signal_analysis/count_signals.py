"""
count_signals.py — AI-Klassifikation des PyPI/GitHub-Oekosystems
====================================================================

Verwendeter Datensatz: upstream_packages (Ende 2024)

WIE WIRD "KI-PROJEKT" OPERATIONALISIERT? — DIE VIER SIGNALE
===========================================================

    Jedes Signal schaut an einer anderen Stelle in der DB nach.
    Deshalb sind es unterschiedliche Paketmengen und ihre Vereinigung
    ist groesser als jedes Signal allein.

    SIGNAL A — Semantisch: KI-Keywords in der PyPI-Paketbeschreibung
    -----------------------------------------------------------------
      Wo:  depsPackages.packageInformation.description
           = kurzer Beschreibungstext eines Pakets auf pypi.org
           NICHT das GitHub-README. NICHT Commit-Messages.
      Beispiel: "TensorFlow is an open source machine learning framework"
      Methode: MongoDB $regex case-insensitive
               Regex-Pattern mit optionalem Separator [\s\-_]? deckt alle
               typografischen Varianten ab:
                 machine[\s\-_]?learning trifft:
                   "machine learning"   (Leerzeichen — Standard-Prosa)
                   "machine-learning"   (Bindestrich — GitHub-Topic-Stil)
                   "machine_learning"   (Underscore — Python-Variablenname)
      Staerke: Selbstzeugnis des Entwicklers. Wer "LLM" in die Beschreibung
               schreibt, definiert das Paket bewusst als AI.
      Schwaeche: ~28% der Pakete haben gar keine Beschreibung (leer/fehlend).
                 Knappe Beschreibungen wie "Utility for my ML project" werden
                 nicht getroffen obwohl das Paket AI ist.

    SIGNAL A2 — Semantisch: KI-Keywords in der GitHub-Repo-Description
    -------------------------------------------------------------------
      Wo:  depsProjects.description
           = einzeiliger Beschreibungstext direkt unter dem Repo-Titel auf GitHub
           NICHT das README. Dasselbe Keyword-Set wie Signal A.
      Warum zusaetzlich: 51% der Pakete haben keine PyPI-Beschreibung.
           GitHub-Descriptions sind oft sorgfaeltiger gepflegt.
      Achtung: depsProjects enthaelt auch Projekte ohne PyPI-Paket.

    SIGNAL B — Strukturell: KI-Library als direkte Abhaengigkeit
    -------------------------------------------------------------
      Wo:  depsPackagesDependencies.dependencies[].name  (nur depth=1)
           = aus requirements.txt / setup.py / pyproject.toml extrahierte
             direkte Abhaengigkeiten
      depth=1: Entwickler hat "torch" bewusst in requirements geschrieben.
      depth=2+: Transitive Deps (X nutzt Y das torch nutzt) — zu indirekt,
                nicht als Signal gewertet.
      Staerke: Verhaltensbasiert, nicht selbst-berichtet. Ein Paket das torch
               importiert NUTZT tatsaechlich PyTorch — unabhaengig davon ob der
               Entwickler "deep learning" in die Beschreibung schreibt.
      Schwaeche: Erfasst keine Pakete die AI-Logik selbst implementieren
                 (z.B. eigene C++-Extension ohne Python-AI-Library als Dep).

    SIGNAL C — Self-Labeling: GitHub-Topics
    ----------------------------------------
      Wo:  depsProjectsPanel.repoData.topics
           ACHTUNG: Feld fehlt in depsProjects (geprueft via Field-Inventory).
           Nur in depsProjectsPanel verfuegbar (Zeitreihen-Collection).
      Was: Array wie ["machine-learning", "pytorch", "nlp"]

    SIGNAL D — Behavioral: Commit-Messages (nicht implementiert)
    ------------------------------------------------------------
      Wo:  depsProjectsCommits.message
      Zu aufwaendig / lautreich fuer diese Analyse-Stufe.

MENGENLOGIK: WARUM A ∪ B > A UND A ∪ B > B
===========================================

    A und B schauen an VERSCHIEDENEN Orten nach. Deshalb enthalten sie
    unterschiedliche Pakete. Ein Paket kann in A sein ohne in B zu sein
    und umgekehrt.

    Konkretes Beispiel:

      Paket "nlp-toolkit":
        PyPI-Desc: "A toolkit for natural language processing"  → A ✓
        requirements.txt: requests, click, pyyaml              → B ✗
        → NUR in A   (sagt "ich bin NLP", nutzt aber keine schwere AI-Lib)

      Paket "torch-helpers":
        PyPI-Desc: "Utility functions for data processing"      → A ✗
        requirements.txt: torch, torchvision, numpy             → B ✓
        → NUR in B   (nutzt PyTorch, beschreibt sich nicht als AI)

      Paket "bert-classifier":
        PyPI-Desc: "BERT-based text classification"             → A ✓
        requirements.txt: transformers, torch, datasets         → B ✓
        → In BEIDEN  (A ∩ B — staerkstes Signal)

    Formel:  A ∪ B  =  (nur A)  +  (A ∩ B)  +  (nur B)
    Mit unseren echten Zahlen:
      A            = 19.444  Pakete  (Keyword in PyPI-Desc)
      B            = 28.414  Pakete  (AI-Lib als direkte Dep)
      A ∩ B        =  9.888  Pakete  (beide Signale positiv — staerkstes Signal)
      nur A        =  9.556  Pakete  (Selbstbeschreibung ja, AI-Lib-Dep nein)
      nur B        = 18.526  Pakete  (AI-Lib-Dep ja, Selbstbeschreibung nein)
      A ∪ B        = 37.970  Pakete  = HAUPTMASS fuer H7
      Anteil       =   7.24% aller 524.609 PyPI-Pakete

    WARUM "NUR B" NICHT GENAU = B - (A ∩ B):
      B zaehlt Pakete in depsPackagesDependencies (524.609 Eintraege nach Dedup).
      Wenn wir B-Paketnamen in depsPackages nachschlagen, fehlen ~0 Pakete —
      sie existieren im Dependency-Graph aber nicht (mehr) als eigenstaendiges
      PyPI-Paket in depsPackages (geloescht, umbenannt, anderes System-Tag).
      Deshalb: nur_B (18.526) + A∩B (9.888) = 28.414 = B_total. Differenz = 0.

    WARUM UNION FUER H7 (NICHT NUR INTERSECTION)?
      Die Schnittmenge (9.888) waere der "sicherste" AI-Indikator, aber sie
      unterschaetzt die Treatment-Gruppe massiv:
        - 15.971 Pakete nutzen nachweislich torch/sklearn (Signal B),
          haben aber eine leere oder knappe PyPI-Beschreibung
        - 9.556 Pakete schreiben explizit "LLM" oder "neural network",
          haben aber keine schwere AI-Library als direkten Dep
          (z.B. API-Wrapper, eigene Implementierungen)
      Union = vollstaendigste, recall-optimierte Klassifikation.
      Intersection = praeziseste, precision-optimierte Klassifikation.
      In der Thesis: Union als Hauptzahl, Intersection als Robustheitscheck.
      Wenn DiD-Koeffizienten mit Union ~= Koeffizienten mit Intersection:
      -> Klassifikation ist robust gegenueber der Grenzziehung.

DATENBANKSTRUKTUR (upstreamPackages, 1.3 TB, MongoDB):
    Collection                  Inhalt                                 Dedup-Status
    depsPackages                524.609 PyPI-Pakete                    unique (_id={name,system})
    depsPackagesDependencies    Dep-Graph, 5.9M Eintraege              mehrere/Paket (Versionen!)
    depsProjects                235.597 GitHub/GitLab/Bitbucket Repos  unique (_id={name,type})
    depsProjectsPanel           Zeitreihen-Snapshots je Projekt+Monat  mehrere/Projekt (Panel!)
    depsProjectsPanel2          Zweite Panel-Collection                mehrere/Projekt (Panel!)
    depsProjectsCommits         Rohe Commit-Daten                      mehrere/Commit
    depsAdvisories              CVE-Sicherheitsverwundbarkeiten        12.153 Eintraege

DEDUP-REGELN:
    depsPackagesDependencies: $group auf _id.name -> unique Paketnamen
    depsProjectsPanel: $group auf name ("owner/repo") -> unique Projekte

VERBINDUNG PAKET <-> PROJEKT:
    depsPackages.packageInformation.projects[] verlinkt PyPI-Pakete auf GitHub-Repos.
    49% der Pakete (249.948) haben diesen Link. Die anderen 51% haben kein
    verknuepftes GitHub-Repo in der DB (PyPI-only Pakete).

AUSGABE:
    count_signals_results.txt   — menschenlesbar, jede Query mit Erklaerung
    count_signals_results.json  — maschinenlesbar, alle Zahlen
    viz_01_ai_share.png            — Balken: A, B, A∪B, Non-AI nebeneinander
    viz_02_tier_breakdown.png      — Balken: Signal-B-Pakete je Library-Tier
    viz_03_top_keywords.png        — Balken: Top-20 Keywords in descriptions
    viz_04_timeline.png            — Linie: Neue Pakete/Jahr (AI vs. alle)
    viz_05_top_dep_libs.png        — Balken: Top-20 AI-Libraries in Deps
    viz_06_venn_breakdown.png      — Venn: Segmente Nur-A / A∩B / Nur-B mit Code-Erklaerung
"""

import re
import json
import time
import sys

import matplotlib
matplotlib.use("Agg")   # kein Display (server/CI)
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib as mpl
import numpy as np

# DejaVu Sans unterstützt Umlaute (ä, ö, ü, ß) — Standard in matplotlib
mpl.rcParams["font.family"] = "DejaVu Sans"

from pymongo import MongoClient
from datetime import datetime, timezone
from pathlib import Path
import argparse as _argparse


# =============================================================================
# KONFIGURATION
# =============================================================================
import sys as _sys
from pathlib import Path, Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from common.db_config   import get_mongo_uri
from common.paths       import get_output_dir
from common.compat_v2   import get_deps_collection, get_topics_collection

_p = _argparse.ArgumentParser(add_help=False)
_args, _ = _p.parse_known_args()
DB_NAME = "upstreamPackagesV2"
MONGO_URI = get_mongo_uri()

OUT_DIR   = Path(get_output_dir())
OUT_TXT   = OUT_DIR / "count_signals_results.txt"
OUT_JSON  = OUT_DIR / "count_signals_results.json"


# =============================================================================
# SIGNAL B — LIBRARY-KLASSIFIKATION (Tier-System)
# =============================================================================
#
# Drei Tiers mit unterschiedlicher wissenschaftlicher Herleitung.
# Alle Libraries wurden mit verify_pypi_libs.py auf PyPI-Existenz, Aktualitaet
# und eigenem AI-Keyword in ihrer Summary geprueft.
#
# WICHTIG: numpy, pandas, scipy etc. sind BEWUSST NICHT in dieser Liste.
# Begruendung: Dilhara et al. 2021 (TOSEM, DOI 10.1145/3453478) unterscheiden
# explizit zwischen "AI/ML libraries" und "traditional data science libraries".
# numpy/pandas sind Hilfsmittel die auch in Finanz-, Bio-, Physik-Paketen
# vorkommen — sie sind kein spezifisches AI-Signal.

TIER1_DILHARA = [
    # Quelle: Dilhara et al. 2021, Table 1 — Kernliste der ML-Frameworks
    # tensorflow-gpu/theano/mxnet: trotz ABANDONED-Status eingeschlossen,
    # da sie im Datensatz (2016-2021) dominante Signale sind (historische Relevanz)
    "tensorflow", "tensorflow-gpu", "tensorflow-cpu",
    "torch", "torchvision", "torchaudio",
    "keras", "mxnet", "paddlepaddle", "tflearn", "dm-sonnet",
    "theano",
    "scikit-learn",
    "spacy", "nltk",
    # "pattern" NICHT enthalten: Original-CLiPS-Package tot seit ~2019,
    # PyPI-Name seit 2024 von unverwandtem Package belegt
]

TIER2_FOUNDATION = [
    # Quelle: Bommasani et al. 2021 (Stanford HAI, arXiv:2108.07258) — Foundation Models
    # + Wolf et al. 2020 (EMNLP) — HuggingFace Transformers
    # HuggingFace-Oekosystem
    "transformers", "sentence-transformers", "datasets",
    "tokenizers", "accelerate", "peft", "diffusers", "trl",
    "huggingface-hub",
    # LLM-Provider-APIs (direkte Nutzung = sehr starkes Signal)
    "openai", "anthropic", "google-generativeai", "mistralai", "cohere",
    # LLM-Orchestrierung / RAG-Frameworks
    "langchain", "langchain-core", "langchain-community",
    "llama-index", "llama-index-core", "llama-cpp-python",
    "haystack-ai", "litellm", "guidance",
    "dspy",
    # Agent-Frameworks
    "crewai", "pyautogen", "autogen", "autogen-agentchat",
    "smolagents", "pydantic-ai",
    # Structured Output / LLM-Tooling
    "instructor",
]

TIER3_ECOSYSTEM = [
    # ML-Oekosystem-Erweiterungen — gute Praezision, breitere Abdeckung
    # Alternative Deep-Learning-Frameworks
    "jax", "flax", "pytorch-lightning", "fastai", "timm", "torch-geometric",
    # LLM-Training-Optimierung (Memory-Efficiency, LoRA etc.)
    "deepspeed", "bitsandbytes", "unsloth",
    # Klassisches ML (eigenstaendige ML-Tools, nicht bloss Statistik)
    "xgboost", "lightgbm", "catboost", "imbalanced-learn",
    # NLP-Oekosystem
    "gensim",
    # Vektor-Datenbanken & RAG-Infrastruktur
    "chromadb", "qdrant-client", "faiss-cpu",
    "pymilvus", "weaviate-client", "pinecone",
    # MLOps (Experiment-Tracking, Monitoring, Serving)
    "mlflow", "wandb", "optuna", "evidently", "bentoml",
    # Reinforcement Learning
    "stable-baselines3",
]

ALL_AI_LIBS = TIER1_DILHARA + TIER2_FOUNDATION + TIER3_ECOSYSTEM

TIER_MAP = {
    **{lib: "tier1_dilhara"    for lib in TIER1_DILHARA},
    **{lib: "tier2_foundation" for lib in TIER2_FOUNDATION},
    **{lib: "tier3_ecosystem"  for lib in TIER3_ECOSYSTEM},
}


# =============================================================================
# SIGNAL A — KEYWORD-KLASSIFIKATION
# =============================================================================
#
# WO WIRD GESUCHT:
#   Collection: depsPackages
#   Feld:       packageInformation.description
#   Das ist der kurze Beschreibungstext des PyPI-Pakets — sichtbar auf pypi.org.
#   Beispiel: "TensorFlow is an open source machine learning framework for everyone."
#   NICHT das GitHub-README, NICHT Commit-Messages.
#
# WARUM DIESES FELD:
#   Entwickler beschreiben ihr Paket selbst. Wenn jemand "machine learning" in
#   die PyPI-Beschreibung schreibt, ist das ein bewusstes Selbstzeugnis.
#   Das Feld ist kurz (~1-3 Saetze) und praezise — wenig Rauschen.
#
# REGEX-STRATEGIE:
#   Pattern wie machine[\s\-_]?learning treffen:
#     "machine learning"  (Leerzeichen)
#     "machine-learning"  (Bindestrich, GitHub-Topic-Style)
#     "machine_learning"  (Underscore, Python-Variable-Style)
#   MongoDB-Option: $options: "i" = case-insensitive
#
# ZWEI KONFIDENZ-STUFEN (fuer Sensitivitaetsanalyse in der Thesis):
#
#   HIGH_CONF: Begriffe, die in PyPI-Descriptions praktisch ausschliesslich
#   in AI/ML-Paketen auftauchen. Falsch-Positive sind moglich aber selten.
#   -> Hauptklassifikation
#
#   MEDIUM_CONF: Begriffe mit erhoehtem False-Positive-Risiko:
#     "embedding" taucht auch in Datenbank/Schriften-Paketen auf
#     "cnn" kann Netzwerk-Paket sein
#     "prediction model" kann statistische Prognose sein
#   -> Nur Sensitivitaetscheck: Wie viele Pakete kommen ZUSAETZLICH dazu?

HIGH_CONF_KEYWORDS = {
    # ---- Allgemeiner AI-Begriff ----
    # \bai\b: word boundary verhindert False-Positives wie "detail", "await", "paid"
    "ai_term":                 r"\bai\b",
    # \bml\b: ebenso geschuetzt
    "ml_abbreviation":         r"\bml\b",

    # ---- ML-Paradigmen (LeCun et al. 2015, Nature; Dilhara et al. 2021) ----
    "machine_learning":        r"machine[\s\-_]?learning",
    "deep_learning":           r"deep[\s\-_]?learning",
    "neural_network":          r"neural[\s\-_]?net(?:work)?s?",
    "artificial_intelligence": r"artificial[\s\-_]?intelligence",
    "reinforcement_learning":  r"reinforcement[\s\-_]?learning",
    "transfer_learning":       r"transfer[\s\-_]?learning",

    # ---- LLMs (Bommasani et al. 2021; Brown et al. 2020, GPT-3) ----
    "llm":                     r"\bllms?\b",
    "large_language_model":    r"large[\s\-_]?language[\s\-_]?model",
    "language_model":          r"\blanguage[\s\-_]?model",
    "foundation_model":        r"foundation[\s\-_]?model",
    "generative_ai":           r"gen(?:erative)?[\s\-_]?ai\b",
    "generative_model":        r"generative[\s\-_]?model",

    # ---- Modell-Architekturen (Vaswani et al. 2017; Ho et al. 2020) ----
    "transformer":             r"\btransformer\b",
    "diffusion_model":         r"diffusion[\s\-_]?model",
    "attention_mechanism":     r"attention[\s\-_]?mechanism",
    # GAN = Generative Adversarial Network (Goodfellow et al. 2014)
    "gan":                     r"\bgans?\b",
    # VAE = Variational Autoencoder (Kingma & Welling 2013)
    "vae":                     r"\bvae\b",

    # ---- NLP-Aufgaben ----
    "nlp":                     r"\bnlp\b",
    "natural_language":        r"natural[\s\-_]?language",
    "text_classification":     r"text[\s\-_]?class(?:ification)?",
    "sentiment_analysis":      r"sentiment[\s\-_]?(?:analysis|classification)",
    "named_entity":            r"named[\s\-_]?entity",
    "text_generation":         r"text[\s\-_]?generat(?:ion|or|ive)",
    "tokenization":            r"\btokeniz(?:er|ation|ing)\b",

    # ---- Computer-Vision-Aufgaben ----
    "computer_vision":         r"computer[\s\-_]?vision",
    "object_detection":        r"object[\s\-_]?detect(?:ion|or)",
    "image_classification":    r"image[\s\-_]?class(?:ification)?",
    "image_segmentation":      r"image[\s\-_]?segment(?:ation)?",
    "image_generation":        r"image[\s\-_]?generat(?:ion|ive|or)",

    # ---- Audio/Speech ----
    "speech_recognition":      r"speech[\s\-_]?recogni(?:tion|zer)",
    # TTS: text-to-speech — wird in PyPI-Descriptions so abgekuerzt
    "text_to_speech":          r"text[\s\-_]?to[\s\-_]?speech|\btts\b",

    # ---- LLM-Tooling (Lewis et al. 2020 — RAG; Post-2022-Praxis) ----
    "retrieval_augmented":     r"retrieval[\s\-_]?augmented",
    # \brag\b: in PyPI-Kontext fast immer Retrieval-Augmented Generation
    "rag":                     r"\brag\b",
    "prompt_engineering":      r"prompt[\s\-_]?engineer",
    "vector_store":            r"vector[\s\-_]?(?:store|database|search)",
    "semantic_search":         r"semantic[\s\-_]?search",
    "fine_tuning":             r"fine[\s\-_]?tun(?:ing|ed?|e)\b",
    "pretrained":              r"pre[\s\-_]?train(?:ed?|ing)?\b",
    "chatbot":                 r"chat[\s\-_]?(?:bot|model|assistant)",
    "word_embedding":          r"(?:word|sentence|text)[\s\-_]?embed",

    # ---- Methodisches ML ----
    "gradient_boosting":       r"gradient[\s\-_]?boost(?:ing)?",
    "automl":                  r"auto[\s\-_]?ml",
    "mlops":                   r"\bmlops?\b",

    # ---- Framework-Referenzen in Beschreibungen ----
    # (Entwickler erwaehnen oft das Framework explizit: "wrapper for PyTorch")
    "pytorch_ref":             r"\bpytorch\b",
    "tensorflow_ref":          r"\btensorflow\b",
    "openai_ref":              r"\bopenai\b",
    "langchain_ref":           r"\blangchain\b",
    "huggingface_ref":         r"hugg?ing[\s\-_]?face",

    # ---- Konkrete Grossmodell-Namen (post-2020) ----
    "gpt_versioned":           r"\bgpt[\s\-_]?\d",          # GPT-3, GPT-4, gpt4
    "gpt_generic":             r"\bgpt\b",                   # GPT-based, GPT wrapper
    "bert_ref":                r"\bbert\b",                  # Devlin et al. 2018
    "chatgpt_ref":             r"\bchatgpt\b",
    "gemini_ref":              r"\bgemini\b",                # Google Gemini
    "llama_ref":               r"\bllama[\s\-_]?\d?\b",      # Meta LLaMA 2/3
    "mistral_ref":             r"\bmistral\b",
    "stable_diffusion":        r"stable[\s\-_]?diffusion",
    # Claude mit Zusatz (verhindert Treffer auf "claude" als Eigenname / Vorname)
    "claude_model_ref":        r"\bclaude[\s\-_](?:api|model|3|opus|sonnet|haiku)",
}

MEDIUM_CONF_KEYWORDS = {
    # Erhoehtes False-Positive-Risiko — NUR fuer Sensitivitaets-Vergleich.
    # In der Thesis: "Unsere Hauptzahl (High-Conf) = X. Mit erweitertem
    # Keyword-Set (High+Medium) = Y. Differenz Y-X zeigt wie robust X ist."
    "embedding":          r"\bembedding[s]?\b",    # auch DB-Embeddings, Font-Embeddings
    "ai_agent":           r"\bai[\s\-_]?agent[s]?\b",
    "data_science":       r"data[\s\-_]?science",  # sehr breit
    "hyperparameter":     r"hyper[\s\-_]?parameter",
    "convolutional":      r"\bconvolutional\b",
    "cnn_rnn_lstm":       r"\b(?:cnn|rnn|lstm|gru)\b",  # cnn kann Netz-Paket sein
    "model_inference":    r"model[\s\-_]?inferenc",
    "vector_represent":   r"vector[\s\-_]?(?:represent|similar|space)",
    "scikit_ref":         r"scikit[\s\-_]?learn",
    "sklearn_ref":        r"\bsklearn\b",
    "xgboost_ref":        r"\bxgboost\b",
    "prediction_model":   r"predict(?:ive|ion)[\s\-_]?model",  # auch Finanzprognose
    "inference_engine":   r"inferenc[\s\-_]?engine",
}

# GitHub-Topics fuer Signal C (Projekt-Ebene, lowercase wie GitHub speichert)
AI_TOPICS = [
    "artificial-intelligence", "ai",
    "machine-learning", "ml",
    "deep-learning", "neural-network", "neural-networks",
    "tensorflow", "pytorch", "keras", "jax",
    "scikit-learn", "sklearn",
    "nlp", "natural-language-processing",
    "computer-vision", "image-classification", "object-detection",
    "transformers", "llm", "large-language-model", "large-language-models",
    "openai", "chatgpt", "gpt", "langchain", "rag",
    "reinforcement-learning", "generative-ai", "generative-model",
    "huggingface", "diffusion", "stable-diffusion",
]


def _build_mongo_regex(patterns: dict) -> str:
    """Kombinierter OR-Regex aus allen Pattern-Values fuer eine einzige DB-Query."""
    return "|".join(f"(?:{p})" for p in patterns.values())


HIGH_CONF_REGEX   = _build_mongo_regex(HIGH_CONF_KEYWORDS)
MEDIUM_CONF_REGEX = _build_mongo_regex(MEDIUM_CONF_KEYWORDS)
COMBINED_REGEX    = _build_mongo_regex({**HIGH_CONF_KEYWORDS, **MEDIUM_CONF_KEYWORDS})


# =============================================================================
# HELFER
# =============================================================================

class DualLog:
    """Schreibt synchron in Konsole und Textdatei (ASCII-safe fuer Windows cp1252)."""
    def __init__(self, filepath):
        self.fh = open(filepath, "w", encoding="utf-8")

    def write(self, line=""):
        safe = line.encode("ascii", "replace").decode("ascii")
        print(safe)
        self.fh.write(line + "\n")

    def close(self):
        self.fh.close()


def hdr(title, char="="):
    bar = char * 72
    return f"\n{bar}\n{title}\n{bar}"


def ts():
    return datetime.now().strftime("%H:%M:%S")


def run_count(coll, filt, label, log):
    log.write(f"  [{ts()}] {label} ...")
    t0 = time.time()
    try:
        n = coll.count_documents(filt)
        log.write(f"    => {n:,}  ({time.time()-t0:.1f}s)")
        return n
    except Exception as e:
        log.write(f"    => FEHLER: {e}  ({time.time()-t0:.1f}s)")
        return None


def run_agg(coll, pipeline, label, log, formatter=None, top_n=None):
    log.write(f"  [{ts()}] {label} ...")
    t0 = time.time()
    try:
        rows = list(coll.aggregate(pipeline, allowDiskUse=True))
        display = rows[:top_n] if top_n else rows
        for row in display:
            if formatter:
                log.write(f"    {formatter(row)}")
            else:
                key = row.get("_id", "(null)")
                cnt = row.get("count", row.get("n", 0))
                log.write(f"    {key}: {cnt:,}")
        log.write(f"    ({time.time()-t0:.1f}s, {len(rows)} Zeilen gesamt)")
        return rows
    except Exception as e:
        log.write(f"    => FEHLER: {e}  ({time.time()-t0:.1f}s)")
        return []


def run_agg_count(coll, pipeline, label, log):
    """Fuegt $count ans Ende des Pipelines und gibt Integer zurueck."""
    log.write(f"  [{ts()}] {label} ...")
    t0 = time.time()
    try:
        rows = list(coll.aggregate(pipeline + [{"$count": "n"}],
                                   allowDiskUse=True))
        n = rows[0]["n"] if rows else 0
        log.write(f"    => {n:,}  ({time.time()-t0:.1f}s)")
        return n
    except Exception as e:
        log.write(f"    => FEHLER: {e}  ({time.time()-t0:.1f}s)")
        return None


# =============================================================================
# VISUALISIERUNGEN
# =============================================================================

PLOT_STYLE = {
    "figure.figsize": (10, 6),
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.alpha": 0.4,
    "font.size": 11,
}


def save_fig(name, log):
    path = OUT_DIR / name
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    log.write(f"  Grafik gespeichert: {path.name}")


def viz_ai_share(results, log):
    """
    viz_01: Wie gross ist der AI-Anteil im PyPI-Oekosystem?

    Zeigt die vier Messwerte nebeneinander:
      Signal A (Keyword in description) — semantisches Signal
      Signal B (AI-Lib als Dep) — strukturelles Signal
      A UNION B — Gesamtzahl klassifizierter AI-Pakete (Hauptzahl fuer H7)
      Nicht-AI — Rest des Oekosystems (Kontrollgruppe)
    """
    with plt.rc_context(PLOT_STYLE):
        n_total = results.get("n_pypi_packages", 0)
        n_a     = results.get("signal_a_high_conf", 0) or 0
        n_b     = results.get("signal_b_any_tier", 0) or 0
        n_union = results.get("union_a_or_b", 0) or 0

        categories = ["Signal A\n(Keyword in\nPyPI-Desc.)",
                      "Signal B\n(AI-Lib als\ndirekte Dep.)",
                      "A UNION B\n(Gesamt-AI\nHauptmass)",
                      "Nicht-AI\n(Kontrollgruppe)"]
        values = [n_a, n_b, n_union, max(0, n_total - n_union)]
        colors = ["#4C72B0", "#55A868", "#C44E52", "#CCCCCC"]

        fig, ax = plt.subplots()
        bars = ax.bar(categories, values, color=colors, edgecolor="white", linewidth=0.8)

        for bar, val in zip(bars, values):
            pct = 100 * val / n_total if n_total else 0
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + n_total * 0.005,
                    f"{val:,}\n({pct:.1f}%)",
                    ha="center", va="bottom", fontsize=9)

        ax.set_title("KI-Klassifikation des PyPI-Oekosystems\n"
                     f"(Basis: {n_total:,} unique PyPI-Pakete)\n"
                     "Signal A: Keywords in packageInformation.description | "
                     "Signal B: AI-Library in dependencies (depth=1)",
                     fontsize=10)
        ax.set_ylabel("Anzahl Pakete")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{int(x):,}"))
        save_fig("viz_01_ai_share.png", log)


def viz_tier_breakdown(results, log):
    """
    viz_02: Welche Library-Generation dominiert das AI-Signal?

    Tier 1 = klassisches ML (Dilhara et al. 2021), dominant vor 2020
    Tier 2 = Foundation Models (Bommasani et al. 2021), LLMs + HuggingFace
    Tier 3 = ML-Ökosystem, MLOps, Vektordatenbanken
    Multi-Tier = Pakete die Libraries aus >1 Tier kombinieren
    """
    with plt.rc_context(PLOT_STYLE):
        tiers  = [
            "Tier 1\nKlassisches ML\n(wissenschaftl.\nKerndefinition)",
            "Tier 2\nFoundation Models\n(LLMs,\nHuggingFace)",
            "Tier 3\nML-Ökosystem\n(MLOps,\nVektordatenbanken)",
            "Multi-Tier\nKombination aus\n≥ 2 Tiers",
        ]
        values = [
            results.get("signal_b_tier1", 0) or 0,
            results.get("signal_b_tier2", 0) or 0,
            results.get("signal_b_tier3", 0) or 0,
            results.get("signal_b_multi_tier", 0) or 0,
        ]
        colors = ["#4C72B0", "#DD8452", "#55A868", "#8172B2"]

        fig, ax = plt.subplots()
        bars = ax.bar(tiers, values, color=colors, edgecolor="white")
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.01,
                    f"{val:,}", ha="center", va="bottom", fontsize=10)

        ax.set_title(
            "Signal B: KI-Pakete nach Library-Tier\n"
            "Unique Pakete mit direkter Abhängigkeit (depth=1) zu einer KI-Library\n"
            "Tier-Einteilung nach Dilhara et al. 2021 und Bommasani et al. 2021",
            fontsize=10,
        )
        ax.set_ylabel("Anzahl unique Pakete mit KI-Library als direkter Abhängigkeit")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{int(x):,}"))
        save_fig("viz_02_tier_breakdown.png", log)


def viz_top_keywords(results, log):
    """
    viz_03: Welche AI-Keywords kommen am haeufigsten in PyPI-Descriptions vor?

    Jeder Balken = Anzahl Pakete in depsPackages deren
    packageInformation.description dieses Keyword enthaelt.
    Hilft zu verstehen welche AI-Begriffe Entwickler am meisten nutzen.
    """
    kw_data = results.get("signal_a_per_keyword_high", [])
    if not kw_data:
        log.write("  viz_03: Keine Keyword-Daten verfuegbar.")
        return

    with plt.rc_context(PLOT_STYLE):
        kw_data_sorted = sorted(kw_data, key=lambda x: x["count"], reverse=True)[:20]
        # "ai_term" → "ai", alle anderen: Underscore→Leerzeichen, "_term" entfernen
        def format_kw_label(kw):
            if kw == "ai_term":
                return "ai"
            return kw.replace("_term", "").replace("_", " ")
        labels = [format_kw_label(d["keyword"]) for d in kw_data_sorted]
        values = [d["count"] for d in kw_data_sorted]

        fig, ax = plt.subplots(figsize=(10, 8))
        y_pos = np.arange(len(labels))
        ax.barh(y_pos, values, color="#4C72B0", edgecolor="white")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("Anzahl PyPI-Pakete (Feld: packageInformation.description)")
        ax.set_title("Top-20 KI-Schlüsselbegriffe in PyPI-Paketbeschreibungen\n"
                     "(High-Confidence-Set, Regex, Quelle: depsPackages)",
                     fontsize=11)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{int(x):,}"))
        save_fig("viz_03_top_keywords.png", log)


def viz_timeline(results, log):
    """
    viz_04: Wann wurden AI-Pakete gegruendet? (ChatGPT-Effekt sichtbar?)

    X-Achse: Gruendungsjahr des PyPI-Pakets (packageInformation.createdAt)
    Y-Achse: Anzahl neuer Pakete dieses Jahr
    Rote Linie: AI-Pakete (Signal A, High-Conf)
    Graue Linie: Alle PyPI-Pakete

    Der Sprung nach Nov. 2022 ist die visuelle Vorstufe zum Event-Study-Plot.
    """
    all_years = results.get("q4_packages_per_year", [])
    ai_years  = results.get("q4_ai_packages_per_year", [])
    if not all_years:
        log.write("  viz_04: Keine Zeitreihen-Daten verfuegbar.")
        return

    with plt.rc_context(PLOT_STYLE):
        all_dict = {r["year"]: r["count"] for r in all_years if r["year"]}
        ai_dict  = {r["year"]: r["count"] for r in ai_years  if r["year"]}

        years = sorted(y for y in all_dict if isinstance(y, int) and 2005 <= y <= 2026)
        all_counts = [all_dict.get(y, 0) for y in years]
        ai_counts  = [ai_dict.get(y, 0)  for y in years]

        fig, ax1 = plt.subplots()
        ax2 = ax1.twinx()  # zweite Y-Achse fuer AI-Pakete

        ax1.plot(years, all_counts, marker="o", markersize=3,
                 label="Alle PyPI-Pakete (links)", color="#AAAAAA", linewidth=2)
        ax2.plot(years, ai_counts, marker="o", markersize=4,
                 label="AI-Pakete Signal A (rechts)", color="#C44E52", linewidth=2)

        ax1.axvline(x=2022.9, color="#4C72B0", linestyle="--", alpha=0.7, linewidth=1.5)
        ax1.text(2023.0, max(all_counts) * 0.90, "ChatGPT\nNov. 2022",
                 color="#4C72B0", fontsize=8, va="top")

        ax1.set_title("Neue PyPI-Pakete pro Jahr: KI vs. alle\n"
                      "(Quelle: depsPackages.packageInformation.createdAt)\n"
                      "KI-Pakete = mind. 1 High-Confidence-Keyword in Paketbeschreibung",
                      fontsize=10)
        ax1.set_xlabel("Jahr")
        ax1.set_ylabel("Alle Pakete / Jahr", color="#AAAAAA")
        ax2.set_ylabel("AI-Pakete / Jahr", color="#C44E52")
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

        ax1.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)
        save_fig("viz_04_timeline.png", log)


def viz_venn_breakdown(results, log):
    """
    viz_06: Venn-Diagramm Signal A und B — Woher kommen die 35.415 AI-Pakete?

    WAS DIESE GRAFIK ZEIGT:
      Die drei Segmente der Vereinigung A ∪ B, gestapelt zu einem Balken.
      Daneben zum Vergleich: Signal A allein, Signal B allein (inkl. Geister).

      Segment "Nur A"  (blau):   Pakete mit KI-Keyword in PyPI-Desc ABER
                                  KEINE AI-Library als direkten Dep.
                                  Quelle: depsPackages.packageInformation.description
                                  Code: _id.name NOT IN names_b AND desc MATCHES regex

      Segment "A ∩ B" (lila):   Pakete mit BEIDEN Signalen.
                                  Quelle: beide Collections gleichzeitig positiv.
                                  Code: _id.name IN names_b AND desc MATCHES regex
                                  -> Praezisester AI-Indikator (Robustheitscheck)

      Segment "Nur B"  (gruen):  Pakete mit AI-Library als Dep ABER KEIN Keyword
                                  in PyPI-Desc (knappe/leere Beschreibung).
                                  Quelle: depsPackagesDependencies + depsPackages
                                  Code: _id.name IN names_b AND desc NOT MATCHES regex

      Balken "Signal B gesamt": B_total aus depsPackagesDependencies nach $group.
                                  Enthaelt zusaetzlich ~2.555 "Geister-Pakete" die
                                  im Dep-Graph existieren aber nicht in depsPackages
                                  (geloeschte/umbenannte PyPI-Pakete).

    WARUM IST NUR-B < B - (A∩B)?
      B_total (28.414) kommt aus depsPackagesDependencies.
      Wenn diese Namen in depsPackages nachgeschlagen werden, fehlen ~2.555.
      Diese Differenz = Pakete im Dep-Graph ohne PyPI-Stammdatensatz.
      Deshalb: Nur-B (15.971) + A∩B (9.888) = 25.859 < B_total (28.414).

    FUER DIE THESIS:
      Union = Treatment-Gruppe H7 (recall-optimiert, vollstaendig)
      Intersection = Robustheitscheck (precision-optimiert, konservativ)
      Wenn DiD-Koeffizienten stabil bleiben: Klassifikation ist robust.
    """
    n_only_a   = results.get("only_signal_a", 0) or 0
    n_intersect = results.get("intersect_a_and_b", 0) or 0
    n_only_b   = results.get("only_signal_b", 0) or 0
    n_union    = results.get("union_a_or_b", 0) or 0
    n_a_total  = results.get("signal_a_high_conf", 0) or 0
    n_b_total  = results.get("signal_b_any_tier", 0) or 0
    n_ghosts   = results.get("signal_b_not_in_depspackages", 0) or 0
    n_total    = results.get("n_pypi_packages", 1) or 1

    if not n_union:
        log.write("  viz_06: Keine Venn-Daten verfuegbar.")
        return

    with plt.rc_context(PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(12, 8))

        col_a     = "#4C72B0"   # blau = nur A
        col_ab    = "#8172B2"   # lila = Schnittmenge
        col_b     = "#55A868"   # grün = nur B
        col_ghost = "#CCCCCC"   # grau = Geister

        width = 0.5

        # Balken 0: Signal A gesamt = Nur-A + A∩B
        ax.bar(0, n_only_a,    width, color=col_a,     edgecolor="white", label="Nur A")
        ax.bar(0, n_intersect, width, bottom=n_only_a,
               color=col_ab,   edgecolor="white", label="A ∩ B (beide Signale)")

        # Balken 1: A ∪ B = Nur-A + A∩B + Nur-B
        ax.bar(1, n_only_a,    width, color=col_a,   edgecolor="white")
        ax.bar(1, n_intersect, width, bottom=n_only_a,
               color=col_ab,   edgecolor="white")
        ax.bar(1, n_only_b,    width, bottom=n_only_a + n_intersect,
               color=col_b,    edgecolor="white", label="Nur B")

        # Balken 2: Signal B gesamt = A∩B + Nur-B + Geister
        ax.bar(2, n_intersect, width, color=col_ab,    edgecolor="white")
        ax.bar(2, n_only_b,    width, bottom=n_intersect,
               color=col_b,    edgecolor="white")
        ax.bar(2, n_ghosts,    width, bottom=n_intersect + n_only_b,
               color=col_ghost, edgecolor="white",
               label=f"Geister ({n_ghosts:,}): im Dep-Graph, nicht in depsPackages")

        # Gesamtzahl über jedem Balken
        for bar_x, val in [(0, n_a_total), (1, n_union), (2, n_b_total)]:
            pct = 100 * val / n_total
            ax.text(bar_x, val + n_total * 0.004,
                    f"{val:,}\n({pct:.1f}%)",
                    ha="center", va="bottom", fontsize=9, fontweight="bold")

        # Segment-Labels innerhalb der Balken
        def label_segment(bar_x, bottom, height, text, color="white"):
            if height > n_total * 0.008:
                ax.text(bar_x, bottom + height / 2, text,
                        ha="center", va="center", fontsize=8, color=color,
                        fontweight="bold")

        label_segment(0, 0,                     n_only_a,    f"Nur A\n{n_only_a:,}")
        label_segment(0, n_only_a,              n_intersect, f"A∩B\n{n_intersect:,}")
        label_segment(1, 0,                     n_only_a,    f"Nur A\n{n_only_a:,}")
        label_segment(1, n_only_a,              n_intersect, f"A∩B\n{n_intersect:,}")
        label_segment(1, n_only_a + n_intersect, n_only_b,   f"Nur B\n{n_only_b:,}")
        label_segment(2, 0,                     n_intersect, f"A∩B\n{n_intersect:,}")
        label_segment(2, n_intersect,           n_only_b,    f"Nur B\n{n_only_b:,}")

        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels([
            f"Signal A\n(Keyword in PyPI-Beschreibung)\n{n_a_total:,} Pakete",
            f"A ∪ B\n(KI-Pakete gesamt — Treatment H7)\n{n_union:,} Pakete",
            f"Signal B\n(KI-Library als direkte Abhängigkeit)\n{n_b_total:,} Pakete",
        ], fontsize=9)
        ax.set_ylabel("Anzahl Pakete")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
        ax.legend(loc="upper right", fontsize=8, framealpha=0.9)

        # Kurze Erklärungsbox unter dem Chart (als Figurtext)
        beschreibung = (
            f"Signal A → Nur A: {n_only_a:,} Pakete beschreiben sich als KI, nutzen aber keine bekannte KI-Library als direkte Abhängigkeit.\n"
            f"Signal A → A ∩ B: {n_intersect:,} Pakete haben beide Signale positiv (stärkstes Indikator, Robustheitscheck).\n"
            f"Signal B → Nur B: {n_only_b:,} Pakete nutzen eine KI-Library, haben aber kein KI-Keyword in der Paketbeschreibung."
        )
        fig.text(0.5, -0.04, beschreibung, ha="center", va="top", fontsize=8.5,
                 wrap=True, style="italic",
                 bbox=dict(boxstyle="round,pad=0.4", facecolor="#F5F5F5",
                           edgecolor="#CCCCCC", alpha=0.8))

        ax.set_title(
            "Klassifikation nach Signalen: Signal A und Signal B\n"
            f"A ∪ B = {n_union:,} KI-Pakete ({100*n_union/n_total:.2f}% aller {n_total:,} PyPI-Pakete) — Treatment-Gruppe für H7",
            fontsize=11,
        )

        save_fig("viz_06_venn_breakdown.png", log)


def viz_top_dep_libs(results, log):
    """
    viz_05: Welche AI-Libraries tauchen am haeufigsten als direkte Dep auf?

    Jeder Balken = Anzahl unique Pakete in depsPackagesDependencies,
    die diese Library als depth=1-Abhaengigkeit haben.
    Farbe zeigt den Tier (blau=T1, orange=T2, gruen=T3).

    Interpretation: scikit-learn und torch dominieren — das sind die
    "Arbeitstools" der ML-Community. openai und transformers zeigen
    den LLM-Boom.
    """
    lib_data = results.get("signal_b_top_libs", [])
    if not lib_data:
        log.write("  viz_05: Keine Library-Daten verfuegbar.")
        return

    with plt.rc_context(PLOT_STYLE):
        lib_data_sorted = sorted(lib_data, key=lambda x: x["count"], reverse=True)[:20]
        labels = [d["lib"] for d in lib_data_sorted]
        values = [d["count"] for d in lib_data_sorted]

        tier_colors = {
            "tier1_dilhara":    "#4C72B0",
            "tier2_foundation": "#DD8452",
            "tier3_ecosystem":  "#55A868",
        }
        colors = [tier_colors.get(TIER_MAP.get(lib, "tier3_ecosystem"), "#888888")
                  for lib in labels]

        fig, ax = plt.subplots(figsize=(10, 8))
        y_pos = np.arange(len(labels))
        ax.barh(y_pos, values, color=colors, edgecolor="white")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("Anzahl unique Pakete mit dieser Library als depth=1-Dep.\n"
                      "(Feld: depsPackagesDependencies.dependencies[].name)")
        ax.set_title("Top-20 AI-Libraries in direkten Abhaengigkeiten\n"
                     "(Signal B, depsPackagesDependencies, $group auf _id.name)",
                     fontsize=11)

        from matplotlib.patches import Patch
        legend_elements = [
            Patch(color="#4C72B0", label="Tier 1 — Dilhara et al. 2021"),
            Patch(color="#DD8452", label="Tier 2 — Foundation Models (Bommasani 2021)"),
            Patch(color="#55A868", label="Tier 3 — ML-Oekosystem"),
        ]
        ax.legend(handles=legend_elements, loc="lower right", fontsize=9)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
        save_fig("viz_05_top_dep_libs.png", log)


# =============================================================================
# HAUPTPROGRAMM
# =============================================================================

def main():
    log = DualLog(OUT_TXT)
    results = {}

    log.write(f"count_signals.py — Start: {datetime.now().isoformat(timespec='seconds')}")
    log.write(f"DB: {DB_NAME}")
    log.write(f"Tier-1 ({len(TIER1_DILHARA)} Libs): {TIER1_DILHARA}")
    log.write(f"Tier-2 ({len(TIER2_FOUNDATION)} Libs): {TIER2_FOUNDATION}")
    log.write(f"Tier-3 ({len(TIER3_ECOSYSTEM)} Libs): {TIER3_ECOSYSTEM}")
    log.write(f"High-Conf-Keywords: {len(HIGH_CONF_KEYWORDS)}")
    log.write(f"Medium-Conf-Keywords: {len(MEDIUM_CONF_KEYWORDS)}")

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]
    db.command("ping")
    log.write("Verbunden.\n")

    packages  = db["depsPackages"]
    projects  = db["depsProjects"]
    pkg_deps  = get_deps_collection(db)
    proj_panel = get_topics_collection(db)  # Signal C: V1=depsProjectsPanel, V2=depsProjects

    def normalize_github_url(url: str | None) -> str | None:
        if not url:
            return None
        url = url.strip().lower()
        url = url.replace("http://", "https://")
        if url.endswith("/"):
            url = url[:-1]
        if url.endswith(".git"):
            url = url[:-4]
        return url

    def get_pkg_repo_url(doc):
        return normalize_github_url(
            (((doc.get("packageInformation") or {}).get("links") or {}).get("repo"))
            or (((doc.get("links") or {}).get("repo")))
        )

    def get_project_repo_url(doc):
        return normalize_github_url(doc.get("link"))

    project_rows = projects.find({"type": "GITHUB"}, {"link": 1, "description": 1, "stars": 1, "score": 1})
    projects_by_link = {}
    for p in project_rows:
        key = get_project_repo_url(p)
        if key:
            projects_by_link[key] = p

    # Join PyPI-Pakete (depsPackages) mit GitHub-Projekten (depsProjects)
    # ueber die normalisierte Repo-URL statt Namensheuristik.
    pkg_rows = packages.find(
        {"_id.system": "PYPI"},
        {"packageInformation.links.repo": 1, "links.repo": 1}
    )
    linked_project_docs = []
    n_pkg_with_repo_link = 0
    n_pkg_repo_link_matched = 0
    for pkg in pkg_rows:
        pkg_key = get_pkg_repo_url(pkg)
        if not pkg_key:
            continue
        n_pkg_with_repo_link += 1
        proj_doc = projects_by_link.get(pkg_key)
        if proj_doc:
            n_pkg_repo_link_matched += 1
            linked_project_docs.append(proj_doc)

    results["n_pkg_with_repo_link"] = n_pkg_with_repo_link
    results["n_pkg_repo_link_matched"] = n_pkg_repo_link_matched

    log.write(f"  Link-Join: {n_pkg_with_repo_link:,} PyPI-Pakete haben links.repo")
    log.write(f"  Link-Join: {n_pkg_repo_link_matched:,} davon matchen ein depsProjects-Dokument (type=GITHUB)")

    # ── Kennzahl 5: KI-Packages (A oder B) mit validem Repo-Link in depsProjects
    # Nur Repos mit depsProjects-Eintrag haben Panel-Daten fuer spaetere Analysen.
    log.write(f"  Kennzahl 5: KI-Packages (A oder B) mit validem Repo-Link in depsProjects...")
    ki_pkg_rows = packages.find(
        {
            "_id.system": "PYPI",
            "$or": [
                {"packageInformation.description": {"$regex": HIGH_CONF_REGEX, "$options": "i"}},
                {"packageInformation.dependencies.name": {"$in": ALL_AI_LIBS}},            # V1
                {"dependencyInformation.dependencies.package.name": {"$in": ALL_AI_LIBS}}  # V2
            ]
        },
        {"packageInformation.links.repo": 1, "links.repo": 1}
    )
    n_ki_with_repo_link    = 0
    n_ki_repo_link_matched = 0
    ki_linked_project_keys = set()
    for pkg in ki_pkg_rows:
        pkg_key = get_pkg_repo_url(pkg)
        if not pkg_key:
            continue
        n_ki_with_repo_link += 1
        if pkg_key in projects_by_link:
            n_ki_repo_link_matched += 1
            ki_linked_project_keys.add(pkg_key)

    results["n_ki_pkg_with_repo_link"]    = n_ki_with_repo_link
    results["n_ki_pkg_repo_link_matched"] = n_ki_repo_link_matched
    log.write(f"    KI-Packages mit Repo-Link:                {n_ki_with_repo_link:,}")
    log.write(f"    davon Link matched in depsProjects (KZ5): {n_ki_repo_link_matched:,}")
    if n_ki_with_repo_link:
        log.write(f"    Match-Rate: {100*n_ki_repo_link_matched/n_ki_with_repo_link:.1f}%")

    # =========================================================================
    # BLOCK 1 — GRUNDGROESSEN
    # =========================================================================
    # Was: Rohe Dokumentenzahlen pro Collection
    # Warum: Basisgroessen fuer alle Prozentangaben in der Thesis
    # Wo: estimated_document_count (schnell, kein full-scan)
    # =========================================================================
    log.write(hdr("BLOCK 1 — Grundgroessen (rohe Collection-Zahlen)"))

    log.write("\n  depsPackages: Jedes Dokument = ein unique PyPI-Paket.")
    log.write("  _id = {name, system} — kein Dedup noetig.")
    n_pypi_raw = run_count(packages, {"_id.system": "PYPI"},
                           "PyPI-Pakete gesamt (depsPackages)", log)

    log.write("\n  depsProjects: Jedes Dokument = ein unique GitHub/GitLab/Bitbucket-Projekt.")
    log.write("  _id = {name: 'owner/repo', type: 'GITHUB'} — kein Dedup noetig.")
    log.write("  Mehrfach-Zeitpunkte sind in depsProjectsPanel, NICHT hier.")
    n_gh_raw = run_count(projects, {"type": "GITHUB"},
                         "GitHub-Projekte gesamt (depsProjects)", log)

    log.write("\n  depsPackagesDependencies: MEHRERE Eintraege pro Paket (je Version).")
    log.write("  5.9M Eintraege != 5.9M unique Pakete!")
    log.write("  Dedup via $group auf _id.name liefert unique Pakete (Block 2).")
    n_deps_raw = run_count(pkg_deps, {},
                           "Versionseintraege gesamt (depsPackagesDependencies, raw)", log)

    results.update({
        "n_pypi_raw": n_pypi_raw,
        "n_github_raw": n_gh_raw,
        "n_deps_raw": n_deps_raw,
    })

    # =========================================================================
    # BLOCK 2 — DEDUPLIZIERTE GRUNDGROESSEN
    # =========================================================================
    # Was: Korrekte unique-Zahlen nach Dedup
    # Warum: depsPackagesDependencies zaehlt Versionen, nicht Pakete.
    #        Ein Paket mit 10 Versionen hat 10 Eintraege. Wir brauchen
    #        aber "wie viele PAKETE nutzen AI-Libraries" — daher $group.
    # Methode: $group auf _id.name aggregiert alle Versionen eines Pakets
    # =========================================================================
    log.write(hdr("BLOCK 2 — Deduplizierte Grundgroessen"))

    log.write("\n  depsPackages: bereits unique (kein Dedup).")
    results["n_pypi_packages"] = n_pypi_raw

    log.write("\n  depsPackagesDependencies: $group auf _id.name")
    log.write("  -> Wie viele unique Paket-NAMEN sind im Dependency-Graph?")
    log.write("  (Unterschied zu Block 1: 5.9M Eintraege vs. X unique Pakete)")
    n_deps_unique = run_agg_count(pkg_deps, [
        {"$group": {"_id": "$_id.name"}},
    ], "unique Paketnamen in depsPackagesDependencies", log)
    results["n_deps_unique_packages"] = n_deps_unique

    if n_pypi_raw and n_deps_unique:
        pct = 100 * n_deps_unique / n_pypi_raw
        log.write(f"    => {pct:.1f}% der PyPI-Pakete sind im Dependency-Graph enthalten")
        log.write(f"    (Rest: Pakete ohne requirements.txt oder nie als Dep genutzt)")

    log.write("\n  depsProjects: bereits unique (_id = Compound-Key). Gleich wie Block 1.")
    results["n_projects_unique"] = n_gh_raw

    results.update({
        "n_pypi_packages": n_pypi_raw,
        "n_deps_unique_packages": n_deps_unique,
        "n_projects_unique": n_gh_raw,
    })

    # =========================================================================
    # BLOCK 3 — SIGNAL A: KI-KEYWORDS IN PACKAGE-BESCHREIBUNGEN
    # =========================================================================
    log.write(hdr("BLOCK 3 — Signal A: KI-Keywords in packageInformation.description"))
    log.write("  SIGNAL A: Semantisches Signal")
    log.write("  Wo: depsPackages.packageInformation.description")
    log.write("  Das ist: Der kurze Beschreibungstext auf pypi.org")
    log.write("  Nicht: GitHub-README, Commit-Messages, Topics")

    n_has_desc = run_count(packages, {
        "_id.system": "PYPI",
        "packageInformation.description": {"$exists": True, "$nin": [None, ""]}
    }, "Pakete mit nicht-leerer description", log)
    results["n_packages_with_description"] = n_has_desc
    if n_pypi_raw and n_has_desc:
        log.write(f"    => {100*n_has_desc/n_pypi_raw:.1f}% aller Pakete haben Beschreibung")

    log.write("\n  A1: High-Confidence-Keywords (Hauptmass Signal A)")
    n_high = run_count(packages, {
        "_id.system": "PYPI",
        "packageInformation.description": {"$regex": HIGH_CONF_REGEX, "$options": "i"}
    }, "Pakete mit mind. 1 High-Conf-Keyword in description", log)
    results["signal_a_high_conf"] = n_high
    if n_pypi_raw and n_high:
        log.write(f"    => {100*n_high/n_pypi_raw:.2f}% aller PyPI-Pakete")

    log.write("\n  A3: High+Medium-Keywords (Sensitivitaetscheck)")
    n_combined = run_count(packages, {
        "_id.system": "PYPI",
        "packageInformation.description": {"$regex": COMBINED_REGEX, "$options": "i"}
    }, "Pakete mit mind. 1 Keyword (High+Medium)", log)
    results["signal_a_combined"] = n_combined
    if n_pypi_raw and n_combined and n_high:
        delta = n_combined - n_high
        log.write(f"    => Delta zu High-Conf: +{delta:,} Pakete ({100*delta/n_high:.1f}% mehr)")

    log.write("\n  A4: Einzelne Keywords (fuer viz_03)")
    kw_counts = []
    for kw_name, pattern in HIGH_CONF_KEYWORDS.items():
        n = run_count(packages, {
            "_id.system": "PYPI",
            "packageInformation.description": {"$regex": pattern, "$options": "i"}
        }, f"    keyword='{kw_name}'", log)
        if n:
            kw_counts.append({"keyword": kw_name, "count": n, "pattern": pattern})
    kw_counts.sort(key=lambda x: x["count"], reverse=True)
    results["signal_a_per_keyword_high"] = kw_counts

    # =========================================================================
    # BLOCK 3b — SIGNAL A2: KI-KEYWORDS IN GITHUB-REPO-DESCRIPTION
    # =========================================================================
    # Was: Dieselben High-Conf-Keywords, aber in der GitHub-Repo-Beschreibung
    # Wo:  depsProjects.description
    #      = Der einzeilige Beschreibungstext direkt unter dem Repo-Titel auf GitHub
    #        (nicht das README — das ist ein separates Feld/Dokument)
    #      Beispiel: "A PyTorch implementation of BERT for NLP tasks"
    # Warum zusaetzlich zu Signal A:
    #      48.661 Pakete (ca. 51%) haben KEINE PyPI-Beschreibung.
    #      Viele Entwickler pflegen aber ihre GitHub-Repo-Description sorgfaeltiger
    #      als die PyPI-Summary.
    #      Ausserdem: GitHub-Description wird vom Entwickler fuer ein menschliches
    #      Publikum geschrieben — nicht als kurzer Tech-Steckbrief.
    # Verbindung zu Signal A:
    #      Beide Signale arbeiten unabhaengig. Ein Paket kann:
    #        - Nur A:  gute PyPI-Desc, knappe GitHub-Desc
    #        - Nur A2: keine PyPI-Desc, aber gute GitHub-Desc
    #        - Beide:  vollstaendig dokumentiertes AI-Paket
    # Achtung: depsProjects enthaelt nicht nur PyPI-verknuepfte Projekte.
    #          Nicht jedes GitHub-Projekt in depsProjects hat ein PyPI-Paket.
    # =========================================================================
    log.write(hdr("BLOCK 3b — Signal A2: KI-Keywords in GitHub-Repo-Description"))
    log.write("  SIGNAL A2: Semantisches Signal auf Projekt-Ebene")
    log.write("  Wo: depsProjects.description")
    log.write("  Das ist: Einzeiliger Beschreibungstext unter dem GitHub-Repo-Titel")
    log.write("  Beispiel: 'A PyTorch implementation of BERT for NLP classification'")
    log.write("  Nicht: README (separates Dokument), Commit-Messages, Topics")
    log.write("  Dieselben High-Conf-Keywords wie Signal A (packageInformation.description)")
    log.write("  -> Direkt vergleichbar: Wo beschreiben Entwickler ihr Paket expliziter?")

    high_conf_re = re.compile(HIGH_CONF_REGEX, re.IGNORECASE)

    n_gh_has_desc = sum(1 for p in linked_project_docs if p.get("description"))
    results["n_github_with_description"] = n_gh_has_desc
    if n_pkg_repo_link_matched and n_gh_has_desc:
        log.write(f"    => {100*n_gh_has_desc/n_pkg_repo_link_matched:.1f}% der PyPI-verknuepften GitHub-Projekte haben Beschreibung")

    log.write("\n  A2a: High-Conf-Keywords in GitHub-Description (Hauptmass)")
    n_a2_high = sum(1 for p in linked_project_docs
                    if p.get("description") and high_conf_re.search(p["description"]))
    results["signal_a2_github_high_conf"] = n_a2_high
    if n_pkg_repo_link_matched and n_a2_high:
        log.write(f"    => {100*n_a2_high/n_pkg_repo_link_matched:.2f}% der PyPI-verknuepften GitHub-Projekte")

    log.write("\n  A2b: Per-Keyword in GitHub-Description (Vergleich zu PyPI-Description)")
    log.write("  Frage: Welche Keywords kommen auf GitHub haeufiger vor als auf PyPI?")
    kw_counts_gh = []
    for name, pattern in HIGH_CONF_KEYWORDS.items():
        pat_re = re.compile(pattern, re.IGNORECASE)
        n = sum(1 for p in linked_project_docs
                if p.get("description") and pat_re.search(p["description"]))
        log.write(f"    github keyword='{name}' => {n:,}")
        if n:
            kw_counts_gh.append({"keyword": name, "count": n, "pattern": pattern})

    kw_counts_gh.sort(key=lambda x: x["count"], reverse=True)
    results["signal_a2_per_keyword_high"] = kw_counts_gh

    # ── Kennzahl 7: Projects mit KI-Keyword aber NICHT via KI-Package erreichbar
    # = A2 \ (Repos die durch Signal A oder B gefunden wurden)
    # Quantifiziert methodisch warum A2 nicht in die Hauptklassifizierung einfließt:
    # Diese Repos haben kein KI-Package als Bruecke -> keine Versionsdaten,
    # keine native/boosted-Klassifizierung moeglich.
    log.write("\n  Kennzahl 7: Projects mit KI-Keyword (A2) aber NICHT via KI-Package erreichbar")
    log.write("  = Repos die nur durch Repo-Description als KI erkennbar waeren")
    n_a2_only = sum(
        1 for p in linked_project_docs
        if p.get("description")
        and high_conf_re.search(p["description"])
        and get_project_repo_url(p) not in ki_linked_project_keys
    )
    results["n_a2_only_not_via_package"] = n_a2_only
    log.write(f"    => {n_a2_only:,} Projects nur via A2 erreichbar (nicht via KI-Package)")
    if n_a2_high:
        log.write(f"    => {100*n_a2_only/n_a2_high:.1f}% der A2-positiven Projekte waeren A2-only")
    log.write(f"    Limitation: Diese Gruppe fehlt in der Hauptklassifizierung (kein Versionsdatensatz)")

    # =========================================================================
    # BLOCK 4 — SIGNAL B: KI-LIBRARY ALS DIREKTABHAENGIGKEIT
    # =========================================================================
    # Was: Strukturelles Signal — AI-Library in requirements
    # Wo:  depsPackagesDependencies.dependencies[].name  (depth=1)
    #      = aus requirements.txt / setup.py / pyproject.toml extrahierter
    #        Dependency-Name
    # Warum depth=1 (direkte Dep, nicht transitive):
    #      depth=1: Entwickler hat torch bewusst in requirements geschrieben
    #      depth=2+: Paket X nutzt Paket Y das torch nutzt — nicht unser Signal
    # Dedup: $group auf _id.name — jedes Paket wird nur einmal gezaehlt
    #        auch wenn es 10 Versionen mit jeweils torch als Dep hat
    # =========================================================================
    log.write(hdr("BLOCK 4 — Signal B: KI-Library als direkte Abhaengigkeit (depth=1)"))
    log.write("  Einmaliger Scan, danach lokale Aggregation")

    t0 = time.time()
    cursor = pkg_deps.aggregate([
        {"$match": {
            "dependencies": {"$elemMatch": {"name": {"$in": ALL_AI_LIBS}, "depth": 1}}
        }},
        {"$unwind": "$dependencies"},
        {"$match": {"dependencies.name": {"$in": ALL_AI_LIBS}, "dependencies.depth": 1}},
        {"$group": {
            "_id": "$_id.name",
            "libs": {"$addToSet": "$dependencies.name"}
        }},
    ], allowDiskUse=True)

    tier1_set = set(TIER1_DILHARA)
    tier2_set = set(TIER2_FOUNDATION)
    tier3_set = set(TIER3_ECOSYSTEM)

    lib_counts = {}
    pkg_names_b = []
    b_any = b_t1 = b_t2 = b_t3 = b_t12 = 0

    for doc in cursor:
        pkg = doc["_id"]
        libs = set(doc["libs"])
        pkg_names_b.append(pkg)
        b_any += 1
        if libs & tier1_set:
            b_t1 += 1
        if libs & tier2_set:
            b_t2 += 1
        if libs & tier3_set:
            b_t3 += 1
        tiers_hit = sum([bool(libs & tier1_set), bool(libs & tier2_set), bool(libs & tier3_set)])
        if tiers_hit >= 2:
            b_t12 += 1
        for lib in libs:
            lib_counts[lib] = lib_counts.get(lib, 0) + 1

    top20 = sorted(lib_counts.items(), key=lambda x: -x[1])[:20]

    results["signal_b_any_tier"] = b_any
    results["signal_b_tier1"] = b_t1
    results["signal_b_tier2"] = b_t2
    results["signal_b_tier3"] = b_t3
    results["signal_b_multi_tier"] = b_t12
    results["signal_b_top_libs"] = [
        {"lib": lib, "count": cnt, "tier": TIER_MAP.get(lib, "unknown")}
        for lib, cnt in top20
    ]
    results["_pkg_names_b"] = pkg_names_b

    log.write(f"    => {b_any:,} Pakete mit mind. 1 AI-Lib ({time.time()-t0:.1f}s)")

    # =========================================================================
    # BLOCK 5 — UEBERSCHNEIDUNG UND UNION (A INTERSECT B, A UNION B)
    # =========================================================================
    # Was: Venn-Diagramm der beiden Signale
    # Warum: Die UNION (A OR B) ist die Hauptklassifikation fuer H7.
    #        Die INTERSECTION (A AND B) ist ein konservativer Robustheitscheck.
    #
    # Methodischer Hintergrund:
    #   15.000+ Pakete haben NUR Signal B (nutzen torch aber beschreiben sich
    #   nicht als AI) — das sind z.B. Wrapper-Pakete, Utility-Libraries fuer
    #   AI-Projekte, oder Pakete deren Autoren knappe Beschreibungen schreiben.
    #   9.000+ Pakete haben NUR Signal A — beschreiben sich als AI, haben aber
    #   keine bekannte AI-Library als Direktdep (z.B. reine API-Wrapper,
    #   LLM-Tools die nur HTTP-Calls machen, oder eigene Implementierungen).
    #   Union = vollstaendigste Klassifikation.
    # =========================================================================
    log.write(hdr("BLOCK 5 — Ueberschneidung Signal A und Signal B"))
    log.write("  Ziel: Venn-Diagramm der beiden Signale")
    log.write("  A UNION B = Hauptklassifikation fuer H7 (Treatment-Gruppe im DiD)")
    log.write("  A INTERSECT B = konservativer Robustheitscheck")
    log.write("")
    log.write("  Methode:")
    log.write("  1. Alle Paketnamen mit Signal B (AI-Dep) aus depsPackagesDependencies abrufen")
    log.write("  2. In depsPackages pruefen: welche haben zusaetzlich Signal A (Keyword)?")

    # ------------------------------------------------------------------
    # TECHNISCHE UMSETZUNG DES VENN-DIAGRAMMS
    #
    # Problem: A und B kommen aus verschiedenen Collections.
    #   A: depsPackages (524.609 Eintraege, unique)
    #   B: depsPackagesDependencies (5.9M Eintraege, mehrere Versionen pro Paket)
    #
    # Loesung in 3 Schritten:
    #   1. names_b = Liste aller Paketnamen mit Signal B (via $group-Aggregation)
    #      -> Python-Liste mit bis zu 28.414 Strings ("paketname")
    #   2. Schnittmenge: Pakete in depsPackages die IN names_b sind UND
    #      Signal A haben -> A ∩ B
    #   3. Nur-A: Pakete in depsPackages die NICHT IN names_b sind UND
    #      Signal A haben
    #   4. Nur-B: Pakete in depsPackages die IN names_b sind UND
    #      Signal A NICHT haben
    #   5. Union = Nur-A + Schnittmenge + Nur-B
    #
    # WICHTIG: "Nur B" zaehlt Pakete die in BEIDEN Collections vorkommen.
    #   Signal B total (28.414) enthaelt auch Pakete die in depsPackagesDependencies
    #   existieren aber NICHT in depsPackages (geloeschte/umbenannte PyPI-Pakete).
    #   Deshalb gilt: Nur-B (15.971) < B - (A∩B) (18.526). Differenz = 2.555.
    #   Diese 2.555 Pakete sind "geister" im Dep-Graph ohne PyPI-Stammdatensatz.
    # ------------------------------------------------------------------

    log.write("\n  Schritt 1: Paketnamen mit Signal B abrufen...")
    log.write("  (Alle Paketnamen aus depsPackagesDependencies die mind. eine AI-Library")
    log.write("   als depth=1-Dep haben — nach Dedup auf Paketnamen-Ebene)")
    t0 = time.time()
    names_b = results["_pkg_names_b"]
    log.write(f"    => {len(names_b):,} Paketnamen mit Signal B  ({time.time()-t0:.1f}s)")
    log.write(f"    (Diese Namen werden jetzt als Filter in depsPackages verwendet)")

    log.write("\n  Schnittmenge A ∩ B:")
    log.write("  Pakete die IN names_b sind (= haben AI-Lib-Dep)")
    log.write("  UND deren PyPI-description ein High-Conf-Keyword enthaelt")
    log.write("  = staerkstes Signal, beide Tests positiv")
    n_intersect = run_count(packages, {
        "_id.system": "PYPI",
        "_id.name": {"$in": names_b},
        "packageInformation.description": {"$regex": HIGH_CONF_REGEX, "$options": "i"}
    }, "A ∩ B: Signal A AND Signal B", log)
    results["intersect_a_and_b"] = n_intersect

    log.write("\n  Nur A (nicht in B):")
    log.write("  Pakete die NICHT IN names_b sind (kein AI-Lib-Dep bekannt)")
    log.write("  aber deren description ein AI-Keyword enthaelt")
    log.write("  Typische Faelle: LLM-API-Wrapper (nur HTTP-Calls, kein torch)")
    log.write("                   Pakete mit eigener AI-Implementierung (kein extern Dep)")
    log.write("                   Edu-Pakete die ML erklaeren ohne ML zu tun")
    n_only_a = run_count(packages, {
        "_id.system": "PYPI",
        "_id.name": {"$nin": names_b},
        "packageInformation.description": {"$regex": HIGH_CONF_REGEX, "$options": "i"}
    }, "Nur A: Keyword in desc, KEIN AI-Lib-Dep", log)
    results["only_signal_a"] = n_only_a

    log.write("\n  Nur B (nicht in A):")
    log.write("  Pakete die IN names_b sind (haben AI-Lib-Dep)")
    log.write("  aber KEIN High-Conf-Keyword in der description haben")
    log.write("  Typische Faelle: knappe description ('Helper for my project')")
    log.write("                   leere/fehlende description")
    log.write("                   Utility-Pakete die torch nutzen ohne es zu erwaehnen")
    log.write("  HINWEIS: Nur-B < B - (A∩B), weil ~2.555 B-Pakete in depsPackages fehlen")
    n_only_b = run_count(packages, {
        "_id.system": "PYPI",
        "_id.name": {"$in": names_b},
        "packageInformation.description": {
            "$not": {"$regex": HIGH_CONF_REGEX, "$options": "i"}
        }
    }, "Nur B: AI-Lib-Dep, KEIN Keyword in desc", log)
    results["only_signal_b"] = n_only_b

    n_union = (n_only_a or 0) + (n_only_b or 0) + (n_intersect or 0)
    results["union_a_or_b"] = n_union

    # Erklaerung der Differenz: B_total vs. B_in_depsPackages
    b_in_packages = (n_only_b or 0) + (n_intersect or 0)
    b_ghosts = len(names_b) - b_in_packages
    results["signal_b_not_in_depspackages"] = b_ghosts

    log.write(f"\n  VENN-DIAGRAMM (Signal A = PyPI-Desc, Signal B = AI-Lib-Dep):")
    log.write(f"")
    log.write(f"    ┌─────────────────────────────────────────────────┐")
    log.write(f"    │  ALLE {n_pypi_raw:,} PyPI-Pakete                   │")
    log.write(f"    │                                                 │")
    log.write(f"    │  ┌──────────────┬──────────────┐               │")
    log.write(f"    │  │   nur A      │   A und B    │  nur B        │")
    log.write(f"    │  │  {n_only_a:>8,}   │   {n_intersect:>8,}   │  {n_only_b:>8,}   │")
    log.write(f"    │  └──────────────┴──────────────┘               │")
    log.write(f"    │                                                 │")
    log.write(f"    │  Nicht-AI: {(n_pypi_raw or 0) - n_union:>8,}                      │")
    log.write(f"    └─────────────────────────────────────────────────┘")
    log.write(f"")
    log.write(f"    A ∪ B (Treatment-Gruppe H7): {n_union:,}  ({100*n_union/(n_pypi_raw or 1):.2f}%)")
    log.write(f"")
    log.write(f"    Zusatzinfo: {b_ghosts:,} Pakete aus Signal B existieren nicht in")
    log.write(f"    depsPackages (geloescht, umbenannt, kein PYPI-System-Tag).")
    log.write(f"    Diese sind in B={len(names_b):,} enthalten aber nicht in der Union-Rechnung.")

    # =========================================================================
    # BLOCK 6 — SIGNAL C: GITHUB-TOPICS (PROJEKT-EBENE)
    # =========================================================================
    # Was: GitHub-Topics als drittes Signal auf Projektebene
    # Wo:  depsProjectsPanel.repoData.topics
    #      WICHTIG: Dieses Feld existiert in depsProjects NICHT (geprueft via
    #      Field-Inventory in raw_samples.json). Es ist nur in depsProjectsPanel.
    #      In depsProjects: Feld fehlt komplett im Field-Inventory.
    # Warum depsProjectsPanel fuer Topics:
    #      depsProjectsPanel ist die Zeitreihen-Collection (Panel-Daten).
    #      repoData wird dort in jedem Snapshot gespeichert und enthaelt topics.
    #      In depsProjects steht nur das "Stammdokument" ohne vollstaendige repoData.
    # =========================================================================
    log.write(hdr("BLOCK 6 — Signal C: GitHub-Topics"))
    log.write("  SIGNAL C: Self-Labeling auf GitHub")
    log.write("  V1: depsProjectsPanel.repoData.topics | V2: depsProjects.repoData.topics")
    log.write("  compat_v2 liefert einheitlich: { _id: {nameWithOwner}, topics: [...] }")

    # proj_panel ist bereits via get_topics_collection(db) gesetzt
    n_ai_topics_unique = run_agg_count(proj_panel, [
        {"$match": {"topics": {"$in": AI_TOPICS}}},
        {"$group": {"_id": "$_id.nameWithOwner"}},
    ], "Unique Projekte mit AI-Topic", log)

    results.update({
        "n_ai_topics_unique": n_ai_topics_unique,
    })

    if n_gh_raw and n_ai_topics_unique:
        log.write(f"    => {100*n_ai_topics_unique/n_gh_raw:.2f}% aller GitHub-Projekte haben AI-Topic")

    log.write("\n  Top-20 AI-Topics:")
    rows_topics = run_agg(proj_panel, [
        {"$match": {"topics": {"$in": AI_TOPICS}}},
        {"$unwind": "$topics"},
        {"$match": {"topics": {"$in": AI_TOPICS}}},
        {"$group": {"_id": "$topics", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ], "Top-20 AI-Topics", log, top_n=20)
    results["top_ai_topics"] = [{"topic": r["_id"], "count": r["count"]} for r in rows_topics]

    # =========================================================================
    # BLOCK 7 — ZEITLICHE VERTEILUNG
    # =========================================================================
    # Was: Wann wurden Pakete gegruendet? AI-Anteil ueber Zeit?
    # Wo:  depsPackages.packageInformation.createdAt (Unix-Timestamp)
    # Warum: Zeigt den ChatGPT-Effekt (struktureller Bruch nach Nov. 2022)
    #        Grundlage fuer Event-Study-Plot in der Thesis
    # =========================================================================
    log.write(hdr("BLOCK 7 — Zeitliche Verteilung (Gruendungsjahr)"))
    log.write("  Wo: depsPackages.packageInformation.createdAt (Unix-Timestamp)")
    log.write("  Konvertierung: $toDate + $multiply(1000) -> Datetime -> $year")
    log.write("  Filter: > 1.000.000.000 um 0-Werte / fehlerhafte Timestamps auszuschliessen")

    log.write("\n  Alle PyPI-Pakete je Gruendungsjahr:")
    rows_all_years = run_agg(packages, [
        {"$match": {
            "_id.system": "PYPI",
            "packageInformation.createdAt": {"$gt": 1000000000}
        }},
        {"$project": {
            "year": {"$year": {"$toDate": {
                "$multiply": ["$packageInformation.createdAt", 1000]
            }}}
        }},
        {"$group": {"_id": "$year", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ], "Alle Pakete je Jahr", log,
    formatter=lambda r: f"Jahr {r['_id']}: {r['count']:,}")
    results["q4_packages_per_year"] = [
        {"year": r["_id"], "count": r["count"]} for r in rows_all_years
    ]

    log.write("\n  AI-Pakete (Signal A High-Conf) je Gruendungsjahr:")
    log.write("  Zeigt: Ist der AI-Anteil nach Nov. 2022 gestiegen? (visueller Pre-Test H7)")
    rows_ai_years = run_agg(packages, [
        {"$match": {
            "_id.system": "PYPI",
            "packageInformation.createdAt": {"$gt": 1000000000},
            "packageInformation.description": {"$regex": HIGH_CONF_REGEX, "$options": "i"}
        }},
        {"$project": {
            "year": {"$year": {"$toDate": {
                "$multiply": ["$packageInformation.createdAt", 1000]
            }}}
        }},
        {"$group": {"_id": "$year", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ], "AI-Pakete je Gruendungsjahr", log,
    formatter=lambda r: f"Jahr {r['_id']}: {r['count']:,}")
    results["q4_ai_packages_per_year"] = [
        {"year": r["_id"], "count": r["count"]} for r in rows_ai_years
    ]

    # =========================================================================
    # BLOCK 8 — VISUALISIERUNGEN
    # =========================================================================
    log.write(hdr("BLOCK 8 — Visualisierungen (Matplotlib PNG-Export)"))
    log.write("  Alle Grafiken werden im selben Ordner wie das Script gespeichert.")

    viz_ai_share(results, log)
    viz_tier_breakdown(results, log)
    viz_top_keywords(results, log)
    viz_timeline(results, log)
    viz_top_dep_libs(results, log)
    viz_venn_breakdown(results, log)

    # =========================================================================
    # ZUSAMMENFASSUNG
    # =========================================================================
    log.write(hdr("ZUSAMMENFASSUNG UND INTERPRETATION", char="#"))

    n_total    = results.get("n_pypi_packages") or 0
    n_dep_uniq = results.get("n_deps_unique_packages") or 0
    n_proj     = results.get("n_projects_unique") or 0
    n_a        = results.get("signal_a_high_conf") or 0
    n_b        = results.get("signal_b_any_tier") or 0
    n_int      = results.get("intersect_a_and_b") or 0
    n_uni      = results.get("union_a_or_b") or 0
    n_c        = results.get("n_ai_topics_unique") or 0
    n_only_a   = results.get("only_signal_a") or 0
    n_only_b   = results.get("only_signal_b") or 0

    def pct(a, b): return f"{100*a/b:.2f}%" if b else "n/a"

    log.write(f"\n  GRUNDGROESSEN:")
    log.write(f"    PyPI-Pakete (unique):                 {n_total:>10,}")
    log.write(f"    Pakete im Dep-Graph (unique):         {n_dep_uniq:>10,}  ({pct(n_dep_uniq, n_total)})")
    log.write(f"    GitHub-Projekte:                      {n_proj:>10,}")

    log.write(f"\n  SIGNAL A — Keywords in packageInformation.description:")
    log.write(f"    High-Conf (Hauptmass):                {n_a:>10,}  ({pct(n_a, n_total)})")
    log.write(f"    High+Medium (Sensitivitaet):          {(results.get('signal_a_combined') or 0):>10,}"
              f"  ({pct(results.get('signal_a_combined') or 0, n_total)})")
    log.write(f"    Delta Medium:                         {(results.get('signal_a_combined') or 0) - n_a:>10,}")

    log.write(f"\n  SIGNAL B — AI-Library als depth=1-Dep (depsPackagesDependencies):")
    log.write(f"    Alle Tiers:                           {n_b:>10,}  ({pct(n_b, n_dep_uniq)} der Dep-Pakete)")
    log.write(f"    Tier 1 (Dilhara 2021):                {(results.get('signal_b_tier1') or 0):>10,}")
    log.write(f"    Tier 2 (Foundation Models):           {(results.get('signal_b_tier2') or 0):>10,}")
    log.write(f"    Tier 3 (ML-Oekosystem):               {(results.get('signal_b_tier3') or 0):>10,}")
    log.write(f"    Multi-Tier (T1+T2):                   {(results.get('signal_b_multi_tier') or 0):>10,}")

    log.write(f"\n  KENNZAHL 5 — KI-Packages mit validem Repo-Link in depsProjects:")
    n_kz5 = results.get("n_ki_pkg_repo_link_matched") or 0
    n_ki_link = results.get("n_ki_pkg_with_repo_link") or 0
    log.write(f"    KI-Packages mit Repo-Link:            {n_ki_link:>10,}")
    log.write(f"    davon in depsProjects gefunden (KZ5): {n_kz5:>10,}  ({pct(n_kz5, n_ki_link)} der KI-Packages mit Link)")
    log.write(f"    Bedeutung: Nur diese Repos koennen in Aktivitaets- und Regressionsanalyse einfliessen.")

    log.write(f"\n  KONTROLLE A2 — Keywords in GitHub-Repo-Description (nicht in Hauptklassifizierung):")
    n_a2 = results.get("signal_a2_github_high_conf") or 0
    n_a2_only = results.get("n_a2_only_not_via_package") or 0
    log.write(f"    GitHub-Projekte mit AI-Keyword:       {n_a2:>10,}  ({pct(n_a2, n_proj)})")
    log.write(f"    (Vergleich: Signal A in PyPI-Desc:    {n_a:>10,}  ({pct(n_a, n_total)}))")
    log.write(f"\n  KENNZAHL 7 — Projects nur via A2 erreichbar (nicht via KI-Package):")
    log.write(f"    A2-only (KZ7):                        {n_a2_only:>10,}  ({pct(n_a2_only, n_a2)} der A2-positiven)")
    log.write(f"    Limitation: Diese Gruppe fehlt in Hauptklassifizierung (keine Versionsdaten).")

    log.write(f"\n  SIGNAL C — GitHub-Topics (depsProjectsPanel):")
    log.write(f"    Unique Projekte mit AI-Topic:         {n_c:>10,}  ({pct(n_c, n_proj)})")

    log.write(f"\n  VENN-DIAGRAMM A und B:")
    log.write(f"    Nur Signal A:                         {n_only_a:>10,}")
    log.write(f"    Nur Signal B:                         {n_only_b:>10,}")
    log.write(f"    Signal A AND B:                       {n_int:>10,}")
    log.write(f"    Signal A UNION B (HAUPTMASS H7):      {n_uni:>10,}  ({pct(n_uni, n_total)})")

    log.write(f"\n  INTERPRETATION:")
    log.write(f"    {pct(n_uni, n_total)} der PyPI-Pakete haben eine nachweisbare KI-Komponente.")
    log.write(f"    Das sind die {n_uni:,} Pakete die als Treatment-Gruppe in H7 dienen.")
    log.write(f"    Die {n_total - n_uni:,} Nicht-KI-Pakete bilden die Kontrollgruppe.")
    log.write(f"    Robustheitscheck: Intersection A AND B = {n_int:,} ({pct(n_int, n_total)})")
    log.write(f"    -> Ergebnis stabil zwischen {pct(n_int, n_total)} und {pct(n_uni, n_total)}")

    log.write(f"\nFertig: {datetime.now().isoformat(timespec='seconds')}")
    log.write(f"Textdump:  {OUT_TXT}")
    log.write(f"JSON-Dump: {OUT_JSON}")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    log.close()
    client.close()


if __name__ == "__main__":
    main()
