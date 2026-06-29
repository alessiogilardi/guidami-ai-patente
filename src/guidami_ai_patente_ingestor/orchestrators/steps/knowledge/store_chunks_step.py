"""Step che persiste i KnowledgeChunk su DB con full-reload per-source."""

import logging
from typing import cast

from commons.entities.knowledge import KnowledgeChunk
from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import KnowledgeChunkStoreRepository

logger = logging.getLogger(__name__)


class StoreChunksStep(Step):
    """Persiste i chunk in `knowledge_chunks` con full-reload della sola source.

    Domain-specific: a differenza del generico `DbStoreStep` (che fa TRUNCATE
    dell'intera tabella), cancella solo i chunk della `source` corrente e poi li
    re-inserisce. Così run su source diverse non si sovrascrivono a vicenda.
    """

    def __init__(
        self,
        name: str,
        repository: KnowledgeChunkStoreRepository,
        source: str,
    ) -> None:
        """Inietta il repository di store e la source della run.

        Args:
            name: Nome univoco dello step nel flow.
            repository: Repository di scrittura su `knowledge_chunks`.
            source: Source il cui contenuto va sostituito (delete-by-source + insert).
        """
        super().__init__(name)
        self._repository = repository
        self._source = source

    def execute(self, context: FlowContext) -> None:
        """Legge `CHUNK_ENTITIES`, cancella i chunk della source e re-inserisce.

        Args:
            context: Shared pipeline context.
        """
        chunks = cast(list[KnowledgeChunk], context.get(context_keys.CHUNK_ENTITIES))
        self._repository.delete_source(self._source)
        self._repository.bulk_insert(chunks)
        logger.info(f"Stored {len(chunks)} chunks for source '{self._source}'")

    def get_required_keys(self) -> set[str]:
        """Richiede `CHUNK_ENTITIES` in input."""
        return {context_keys.CHUNK_ENTITIES}

    def get_produced_keys(self) -> set[str]:
        """Nessuna chiave prodotta: è lo step terminale (sink) del flow."""
        return set()
