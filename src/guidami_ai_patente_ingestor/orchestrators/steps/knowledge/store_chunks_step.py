"""Step that persists KnowledgeChunk records to the DB with per-source full-reload."""

import logging
from typing import cast

from flowstep import FlowContext, Step

from domain.entities.knowledge import KnowledgeChunk
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import KnowledgeChunkStoreRepository

logger = logging.getLogger(__name__)


class StoreChunksStep(Step):
    """Persists the chunks to `knowledge_chunks` with full-reload of that source only.

    Domain-specific: unlike the generic `DbStoreStep` (which does a TRUNCATE
    of the entire table), it only deletes the chunks of the current `source`
    and then re-inserts them. This way runs on different sources do not
    overwrite each other.
    """

    def __init__(
        self,
        name: str,
        source: str,
        repository: KnowledgeChunkStoreRepository,
    ) -> None:
        """Injects the run's source and the store repository.

        Args:
            name: Unique step name within the flow.
            source: Source whose content must be replaced (delete-by-source + insert).
            repository: Write repository for `knowledge_chunks`.
        """
        super().__init__(name)
        self._repository = repository
        self._source = source

    def execute(self, context: FlowContext) -> None:
        """Reads `CHUNK_ENTITIES`, deletes the source's chunks, and re-inserts them.

        Args:
            context: Shared pipeline context.
        """
        chunks = cast(list[KnowledgeChunk], context.get(context_keys.CHUNK_ENTITIES))
        self._repository.delete_source(self._source)
        self._repository.bulk_insert(chunks)
        logger.info(f"Stored {len(chunks)} chunks for source '{self._source}'")

    def get_required_keys(self) -> set[str]:
        """Requires `CHUNK_ENTITIES` as input."""
        return {context_keys.CHUNK_ENTITIES}

    def get_produced_keys(self) -> set[str]:
        """No produced key: this is the flow's terminal (sink) step."""
        return set()
