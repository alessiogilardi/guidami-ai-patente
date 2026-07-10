"""Step that assigns embeddings to EmbeddableChunkModel (with domain repealed filter)."""

import logging
from typing import cast

from flowstep import FlowContext, Step

from commons.services.embeddings import EmbeddingService
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableChunkModel
from guidami_ai_patente_ingestor.orchestrators import context_keys

logger = logging.getLogger(__name__)


class EmbedChunksStep(Step):
    """Assigns embeddings to the EmbeddableChunkModel present in `EMBEDDABLE_CHUNKS`.

    Repealed behavior (invariant with respect to the baseline):
    - `embed_repealed=False` (default): only non-repealed chunks receive the vector;
      repealed ones remain with `embedding=None` but are **present** in `EMBEDDABLE_CHUNKS`.
    - `embed_repealed=True`: all chunks are embedded.

    Pure composition: no inheritance from the generic `EmbedStep`.
    """

    def __init__(
        self,
        name: str,
        embed_repealed: bool,
        embedding_service: EmbeddingService,
    ) -> None:
        """Injects the repealed flag and the embedding service.

        Args:
            name: Unique step name within the flow.
            embed_repealed: If True, also embeds repealed chunks.
            embedding_service: Service that computes embeddings in batch.
        """
        super().__init__(name)
        self._embed = embedding_service
        self._embed_repealed = embed_repealed

    def execute(self, context: FlowContext) -> None:
        """Reads `EMBEDDABLE_CHUNKS`, assigns vectors (in place), rewrites `EMBEDDABLE_CHUNKS`.

        Filtered-out repealed chunks remain with `embedding=None` in the full
        list, which is re-inserted into `EMBEDDABLE_CHUNKS` unchanged in length.

        Args:
            context: Shared pipeline context.
        """
        chunks = cast(list[EmbeddableChunkModel], context.get(context_keys.EMBEDDABLE_CHUNKS))
        to_embed = chunks if self._embed_repealed else [c for c in chunks if not c.is_repealed]

        if to_embed:
            vectors = self._embed(to_embed)
            for chunk, vector in zip(to_embed, vectors, strict=True):
                chunk.embedding = vector

        logger.info(
            f"Embedded {len(to_embed)}/{len(chunks)} chunks "
            f"(embed_repealed={self._embed_repealed})"
        )
        context.put(context_keys.EMBEDDABLE_CHUNKS, chunks)

    def get_required_keys(self) -> set[str]:
        """Requires `EMBEDDABLE_CHUNKS` as input."""
        return {context_keys.EMBEDDABLE_CHUNKS}

    def get_produced_keys(self) -> set[str]:
        """Re-declares `EMBEDDABLE_CHUNKS`: updates the chunks with embedding assigned in place.

        Note: FlowValidator emits a benign WARNING 'Produced key overwrites
        an already available key' — expected and non-blocking.
        """
        return {context_keys.EMBEDDABLE_CHUNKS}
