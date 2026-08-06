"""Argument parser for the `ingest` CLI.

Subcommand structure:
    ingest [--config PATH] prepare knowledge --source <cds|cap> [--force] [--dry-run] [--plain]
    ingest [--config PATH] prepare quiz [--force] [--dry-run] [--plain]
    ingest [--config PATH] index knowledge --source <cds|cap> [--dry-run] [--plain]
    ingest [--config PATH] index quiz [--dry-run] [--plain]
    ingest [--config PATH] reset knowledge [--apply]
    ingest [--config PATH] reset quiz [--apply]
    ingest [--config PATH] status [--online]
    ingest [--config PATH] evaluate retrieval [--seed N] [--baseline-repetitions N]
        [--dry-run] [--plain]

`reset` is destructive, so its gate is inverted from every other command: it
previews (no DB connection) by default, and `--apply` is required to actually
run the TRUNCATE. It does not define `--dry-run`.

`--config PATH` (anywhere in argv) points every command at an alternate
`ingestor_config.yaml` instead of the default `configs/ingestor_config.yaml` — e.g.
`configs/ingestor_config.test-data.yaml` to run against the `data/test-data/` subset.
It is parsed out of argv before the command parser below is built (see
`cli/main.py::_parse_config_override`), so it is not defined as an argument here.
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
  reset knowledge [--apply]
      Truncate articles and article_commas (wipe). Previews by default; --apply executes.
  reset quiz [--apply]
      Truncate quiz_questions (full wipe). Previews by default; --apply executes.
  status [--online]
      Show config + per-command readiness.
  evaluate retrieval [--seed N] [--baseline-repetitions N] [--dry-run] [--plain]
      Measure retrieval quality against the quiz bank (spec 0007). --seed/
      --baseline-repetitions override the configured values; omit to use config.

`--dry-run` (on `prepare`/`index`/`evaluate`) prints the step chain the command would
execute and exits: no filesystem writes, no LLM calls, no DB connection is ever opened.

`reset` is destructive, so it inverts that gate: it previews by default (same
no-filesystem/no-DB guarantee as `--dry-run`) and requires `--apply` to actually
truncate.

`--config PATH` (before or after the subcommand) points at an alternate
ingestor_config.yaml, e.g. configs/ingestor_config.test-data.yaml to run against
the data/test-data/ subset instead of the full corpus.

Examples:
  ingest prepare knowledge --source cds
  ingest index quiz
  ingest reset knowledge
  ingest reset knowledge --apply
  ingest status --online
  ingest prepare knowledge --source cds --dry-run
  ingest index quiz --plain
  ingest --config configs/ingestor_config.test-data.yaml prepare knowledge --source cds
  ingest evaluate retrieval --dry-run
  ingest evaluate retrieval --seed 7 --baseline-repetitions 5
"""


def _add_dry_run_flag(entity_parser: argparse.ArgumentParser) -> None:
    """Adds `--dry-run` to a leaf (command, entity) subparser."""
    entity_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the step chain that would run and exit; no filesystem/LLM/DB access.",
    )


def _add_apply_flag(entity_parser: argparse.ArgumentParser) -> None:
    """Adds `--apply` to a `reset` leaf subparser (opt-in destructive gate)."""
    entity_parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually execute the truncation; without it, only prints what would be deleted.",
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
    rst_k = rst_subs.add_parser("knowledge", help="Truncate articles and article_commas tables.")
    _add_apply_flag(rst_k)
    rst_q = rst_subs.add_parser("quiz", help="Truncate quiz_questions table.")
    _add_apply_flag(rst_q)

    # ---- status ----
    status_p = cmd_subs.add_parser("status", help="Show config + per-command readiness.")
    status_p.add_argument(
        "--online",
        action="store_true",
        default=False,
        help="Also ping Postgres and report per-table existence and row count.",
    )

    # ---- evaluate ----
    evaluate_p = cmd_subs.add_parser("evaluate", help="Run the retrieval evaluation harness.")
    eval_subs = evaluate_p.add_subparsers(dest="entity", required=True)
    eval_r = eval_subs.add_parser(
        "retrieval", help="Measure retrieval quality against the quiz bank."
    )
    eval_r.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override the configured random baseline seed (default: use config).",
    )
    eval_r.add_argument(
        "--baseline-repetitions",
        type=int,
        default=None,
        help="Override the configured baseline repetition count (default: use config).",
    )
    _add_dry_run_flag(eval_r)
    _add_plain_flag(eval_r)

    return parser
