"""Argument parser for the `ingest` CLI.

Subcommand structure:
    ingest prepare knowledge --source <cds|cap> [--force]
    ingest prepare quiz [--force]
    ingest index knowledge --source <cds|cap>
    ingest index quiz
    ingest reset knowledge
    ingest reset quiz
    ingest status [--online]
"""

import argparse

from guidami_ai_patente_ingestor.configs import IngestorConfig

_EPILOG = """\
Commands:
  prepare knowledge --source <cds|cap> [--force]   Clean + enrich the knowledge corpus.
  prepare quiz [--force]                           Clean + enrich the quiz bank.
  index knowledge --source <cds|cap>               Embed + store the knowledge corpus.
  index quiz                                       Embed + store the quiz bank.
  reset knowledge                                  Truncate knowledge_chunks (full wipe).
  reset quiz                                       Truncate quiz_questions (full wipe).
  status [--online]                                Show config + per-command readiness.

Examples:
  ingest prepare knowledge --source cds
  ingest index quiz
  ingest reset knowledge
  ingest status --online
"""


def build_parser(config: IngestorConfig) -> argparse.ArgumentParser:
    """Builds the nested-subcommand parser from config-driven source catalogs."""
    parser = argparse.ArgumentParser(
        prog="ingest",
        description="Unified ingestion CLI for guidami-ai-patente.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cmd_subs = parser.add_subparsers(dest="command", required=True)

    # ---- prepare ----
    prepare_p = cmd_subs.add_parser("prepare", help="Run preparation flows.")
    prep_subs = prepare_p.add_subparsers(dest="entity", required=True)

    prep_k = prep_subs.add_parser("knowledge", help="Prepare knowledge corpus.")
    prep_k.add_argument(
        "--source",
        required=True,
        choices=config.knowledge_preparation.sources,
        help="Source to prepare (e.g. 'cds', 'cap').",
    )
    prep_k.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-run even if output already exists.",
    )

    prep_q = prep_subs.add_parser("quiz", help="Prepare quiz bank.")
    prep_q.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-run even if output already exists.",
    )

    # ---- index ----
    index_p = cmd_subs.add_parser("index", help="Run indexing flows.")
    idx_subs = index_p.add_subparsers(dest="entity", required=True)

    idx_k = idx_subs.add_parser("knowledge", help="Index knowledge corpus.")
    idx_k.add_argument(
        "--source",
        required=True,
        choices=config.knowledge_indexing.sources,
        help="Source to index (e.g. 'cds', 'cap').",
    )

    idx_subs.add_parser("quiz", help="Index quiz bank.")

    # ---- reset ----
    reset_p = cmd_subs.add_parser("reset", help="Truncate DB tables (full wipe).")
    rst_subs = reset_p.add_subparsers(dest="entity", required=True)
    rst_subs.add_parser("knowledge", help="Truncate knowledge_chunks table.")
    rst_subs.add_parser("quiz", help="Truncate quiz_questions table.")

    # ---- status ----
    status_p = cmd_subs.add_parser("status", help="Show config + per-command readiness.")
    status_p.add_argument(
        "--online",
        action="store_true",
        default=False,
        help="Also ping Postgres and report per-table existence and row count.",
    )

    return parser
