import logging

import psycopg
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pywire import Autowired, service

from commons.ai.embedding import EmbeddingService
from commons.use_cases import AsyncUseCase
from glossary.configs import GlossaryBlockConfig, GlossaryConfig
from glossary.exceptions import GlossaryBuildError
from glossary.mappers import GlossaryEntryMapper
from glossary.models import BlockOutcome, GlossaryBuildReport, GlossaryBuildRequest
from glossary.repositories import (
    GlossaryBlockReadRepository,
    GlossaryEntryReadRepository,
    GlossaryEntryWriteRepository,
)

from .glossary_extraction_service import GlossaryExtractionService

logger = logging.getLogger(__name__)

# One block's failure must not abort its siblings (FR-7), but only for the runtime
# failure modes a block can actually hit: an exhausted/misbehaving LLM call, a
# Postgres write failure, or invalid data. Anything else (e.g. a TypeError in mapping
# code) is a programming bug and must propagate, not be reported as a "failed block".
_ISOLATED_BLOCK_FAILURES = (
    psycopg.Error,
    ModelHTTPError,
    UnexpectedModelBehavior,
    ValidationError,
)


@service
class GlossaryBuildService(AsyncUseCase[GlossaryBuildRequest, GlossaryBuildReport]):
    """Sequences `build-glossary`'s pipeline, block by block (FR-2, FR-7).

    Never calls the term translator (AD-11) — every row this writes has
    `term_ru = None` (FR-6, enforced by `GlossaryEntryMapper`).
    """

    config: Autowired[GlossaryConfig]
    block_reader: Autowired[GlossaryBlockReadRepository]
    entry_reader: Autowired[GlossaryEntryReadRepository]
    extraction_service: Autowired[GlossaryExtractionService]
    embedding_service: Autowired[EmbeddingService]
    entry_writer: Autowired[GlossaryEntryWriteRepository]

    async def execute(self, request: GlossaryBuildRequest) -> GlossaryBuildReport:
        outcomes: list[BlockOutcome] = []
        failed_labels: list[str] = []
        for block in self.config.blocks:
            label = f"{block.source}/{block.article_number}/{block.comma_number or 'all'}"
            outcome: BlockOutcome | None = None
            try:
                outcome = await self._build_one(block, request.force)
            except _ISOLATED_BLOCK_FAILURES:
                logger.error("Block %s failed", label, exc_info=True)
                failed_labels.append(label)

            if outcome is not None:
                outcomes.append(outcome)

        if failed_labels:
            raise GlossaryBuildError(failed_labels, outcomes)
        return GlossaryBuildReport(outcomes=tuple(outcomes))

    async def _build_one(self, block: GlossaryBlockConfig, force: bool) -> BlockOutcome:
        if not force and self.entry_reader.has_entries_for(block):
            return BlockOutcome(
                source=block.source,
                article_number=block.article_number,
                comma_number=block.comma_number,
                entries_written=0,
                skipped=True,
            )

        glossary_block = self.block_reader.read(block)
        entries = await self.extraction_service(glossary_block)
        embeddings = self.embedding_service([f"{e.term}\n{e.definition}" for e in entries])
        entities = [
            GlossaryEntryMapper.from_extracted_to_entity(entry, block, embedding)
            for entry, embedding in zip(entries, embeddings, strict=True)
        ]
        self.entry_writer.write(block, entities)
        return BlockOutcome(
            source=block.source,
            article_number=block.article_number,
            comma_number=block.comma_number,
            entries_written=len(entities),
            skipped=False,
        )
