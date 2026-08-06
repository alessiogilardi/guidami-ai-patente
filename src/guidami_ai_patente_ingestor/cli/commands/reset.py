"""`ingest reset` dispatch: truncate the target DB table (full wipe)."""

import argparse
import logging

from rich.console import Console

from guidami_ai_patente_ingestor.configs import IngestorConfig

from .. import wiring
from ..rendering import render_dry_run

logger = logging.getLogger(__name__)


def _render_reset_preview(args: argparse.Namespace) -> None:
    """Describes the truncation `--apply` would run, without opening a DB connection."""
    console = Console()
    match args.entity:
        case "knowledge":
            steps = [
                "TRUNCATE article_commas, articles (full wipe, irreversible)",
                "Pass --apply to execute; without it, nothing is deleted.",
            ]
            render_dry_run(console, f"reset {args.entity}", steps)
        case "quiz":
            steps = [
                "TRUNCATE quiz_question_embeddings, quiz_questions (full wipe, irreversible)",
                "Pass --apply to execute; without it, nothing is deleted.",
            ]
            render_dry_run(console, f"reset {args.entity}", steps)


def run_reset(config: IngestorConfig, args: argparse.Namespace) -> None:
    """Dispatch reset subcommand: truncate the target DB table (full wipe).

    Destructive, so the gate is inverted from `prepare`/`index`: without `--apply`
    this only previews the truncation and opens no DB connection; `--apply` is
    required to actually run it.
    """
    if not args.apply:
        _render_reset_preview(args)
        return

    postgres_client = wiring.build_postgres_client(config)
    match args.entity:
        case "knowledge":
            # Combined statement, not two sequential repository .truncate() calls:
            # Postgres refuses to TRUNCATE `articles` while `article_commas`'s FK
            # references it, unless both tables are named in the SAME TRUNCATE
            # statement (PD-13, plans/0001-article-level-storage-plan.md).
            postgres_client.truncate(config.article_commas_table, config.articles_table)
            logger.info("articles and article_commas tables truncated")
        case "quiz":
            # Combined statement, not a single-table repository .truncate() call:
            # Postgres refuses to TRUNCATE `quiz_questions` while
            # `quiz_question_embeddings`'s FK references it, unless both tables
            # are named in the SAME TRUNCATE statement (mirrors the knowledge branch).
            postgres_client.truncate(
                config.quiz_question_embeddings_table, config.quiz_questions_table
            )
            logger.info("quiz_question_embeddings and quiz_questions tables truncated")
