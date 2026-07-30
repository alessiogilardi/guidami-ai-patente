"""`ingest reset` dispatch: truncate the target DB table (full wipe)."""

import argparse
import logging

from rich.console import Console

from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.repositories import (
    KnowledgeChunkStoreRepository,
    QuizQuestionStoreRepository,
)

from .. import wiring
from ..rendering import render_dry_run

logger = logging.getLogger(__name__)


def _render_reset_dry_run(args: argparse.Namespace) -> None:
    """Describes the truncation that would run, without opening a DB connection."""
    console = Console()
    match args.entity:
        case "knowledge":
            steps = ["TRUNCATE knowledge_chunks (full wipe, irreversible in a real run)"]
            render_dry_run(console, f"reset {args.entity}", steps)
        case "quiz":
            steps = ["TRUNCATE quiz_questions (full wipe, irreversible in a real run)"]
            render_dry_run(console, f"reset {args.entity}", steps)


def run_reset(config: IngestorConfig, args: argparse.Namespace) -> None:
    """Dispatch reset subcommand: truncate the target DB table (full wipe)."""
    if args.dry_run:
        _render_reset_dry_run(args)
        return

    postgres_client = wiring.build_postgres_client(config)
    match args.entity:
        case "knowledge":
            KnowledgeChunkStoreRepository(
                config.knowledge_chunks_table, postgres_client
            ).truncate()
            logger.info("knowledge_chunks table truncated")
        case "quiz":
            QuizQuestionStoreRepository(config.quiz_questions_table, postgres_client).truncate()
            logger.info("quiz_questions table truncated")
