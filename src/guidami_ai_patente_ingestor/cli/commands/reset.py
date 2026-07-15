"""`ingest reset` dispatch: truncate the target DB table (full wipe)."""

import argparse
import logging

from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.repositories import (
    KnowledgeChunkStoreRepository,
    QuizQuestionStoreRepository,
)

from .. import wiring

logger = logging.getLogger(__name__)


def run_reset(config: IngestorConfig, args: argparse.Namespace) -> None:
    """Dispatch reset subcommand: truncate the target DB table (full wipe)."""
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
