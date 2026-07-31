"""Argument parser for the `ingest` CLI.

Subcommand structure:
    ingest prepare knowledge --source <cds|cap> [--force] [--dry-run] [--plain]
    ingest prepare quiz [--force] [--dry-run] [--plain]
    ingest index knowledge --source <cds|cap> [--dry-run] [--plain]
    ingest index quiz [--dry-run] [--plain]
    ingest reset knowledge [--dry-run]
    ingest reset quiz [--dry-run]
    ingest status [--online]
"""

import argparse

from guidami_ai_patente_ingestor.configs import IngestorConfig

_EPILOG = """\
Commands:
  prepare knowledge --source <cds|cap> [--force] [--dry-run] [--plain]
      Clean + enrich the knowledge corpus.
  prepare quiz [--force] [--dry-run] [--plain]
      Clean + enrich the quiz bank.
  index knowledge --source <cds|cap> [--dry-run] [--plain]
      Embed + store the knowledge corpus.
  index quiz [--dry-run] [--plain]
      Embed + store the quiz bank.
  reset knowledge [--dry-run]
      Truncate knowledge_chunks (wipe).
  reset quiz [--dry-run]
      Truncate quiz_questions (full wipe).
  status [--online]
      Show config + per-command readiness.

`--dry-run` prints the step chain the command would execute and exits: no
filesystem writes, no LLM calls, no DB connection is ever opened.

Examples:
  ingest prepare knowledge --source cds
  ingest index quiz
  ingest reset knowledge
  ingest status --online
  ingest prepare knowledge --source cds --dry-run
  ingest index quiz --plain
"""


def _add_dry_run_flag(entity_parser: argparse.ArgumentParser) -> None:
    """Adds `--dry-run` to a leaf (command, entity) subparser."""
    entity_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the step chain that would run and exit; no filesystem/LLM/DB access.",
    )


def _add_plain_flag(entity_parser: argparse.ArgumentParser) -> None:
    """Adds `--plain` to a leaf (command, entity) subparser."""
    entity_parser.add_argument(
        "--plain",
        action="store_true",
        default=False,
        help="Disable the live dashboard; emit plain log lines.",
    )


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
    _add_dry_run_flag(prep_k)
    _add_plain_flag(prep_k)

    prep_q = prep_subs.add_parser("quiz", help="Prepare quiz bank.")
    prep_q.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-run even if output already exists.",
    )
    _add_dry_run_flag(prep_q)
    _add_plain_flag(prep_q)

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
    _add_dry_run_flag(idx_k)
    _add_plain_flag(idx_k)

    idx_q = idx_subs.add_parser("quiz", help="Index quiz bank.")
    _add_dry_run_flag(idx_q)
    _add_plain_flag(idx_q)

    # ---- reset ----
    reset_p = cmd_subs.add_parser("reset", help="Truncate DB tables (full wipe).")
    rst_subs = reset_p.add_subparsers(dest="entity", required=True)
    rst_k = rst_subs.add_parser("knowledge", help="Truncate knowledge_chunks table.")
    _add_dry_run_flag(rst_k)
    rst_q = rst_subs.add_parser("quiz", help="Truncate quiz_questions table.")
    _add_dry_run_flag(rst_q)

    # ---- status ----
    status_p = cmd_subs.add_parser("status", help="Show config + per-command readiness.")
    status_p.add_argument(
        "--online",
        action="store_true",
        default=False,
        help="Also ping Postgres and report per-table existence and row count.",
    )

    return parser
