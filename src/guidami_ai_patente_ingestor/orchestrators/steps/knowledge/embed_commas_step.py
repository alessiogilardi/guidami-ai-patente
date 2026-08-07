"""Step that assigns embeddings to EmbeddableArticleComma (with domain repealed filter)."""

import logging
from typing import cast

from flowstep import FlowContext, Step

from commons.ai.embedding import EmbeddingService
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableArticleComma

logger = logging.getLogger(__name__)

# Not yet a context_keys.py constant (added in T-14): EmbedCommasStep reads/writes
# it as a hardcoded literal until then (per plan T-11).
_EMBEDDABLE_ARTICLE_COMMAS_KEY = "embeddable_article_commas"


class EmbedCommasStep(Step):
    """Assigns embeddings to the EmbeddableArticleComma present in `embeddable_article_commas`.

    Repealed behavior:
    - `embed_repealed=False` (default): only non-repealed commas receive the vector;
      repealed ones remain with `embedding=None` but are **present** in the output list.
    - `embed_repealed=True`: all commas are embedded.

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
            embed_repealed: If True, also embeds repealed commas.
            embedding_service: Service that computes embeddings in batch.
        """
        super().__init__(name)
        self._embed_repealed = embed_repealed
        self._embedding_service = embedding_service

    def execute(self, context: FlowContext) -> None:
        """Reads `embeddable_article_commas`, assigns vectors, rewrites the same key.

        Skipped repealed commas remain with `embedding=None` in the output list,
        which is re-inserted unchanged in length.

        Args:
            context: Shared pipeline context.
        """
        commas = cast(list[EmbeddableArticleComma], context.get(_EMBEDDABLE_ARTICLE_COMMAS_KEY))
        to_embed = [comma for comma in commas if self._should_embed(comma)]
        vectors = (
            self._embedding_service.execute([comma.embedded_text for comma in to_embed])
            if to_embed
            else []
        )
        vectors_iter = iter(vectors)
        result = [
            comma.model_copy(update={"embedding": next(vectors_iter)})
            if self._should_embed(comma)
            else comma
            for comma in commas
        ]

        logger.info(
            f"Embedded {len(to_embed)}/{len(commas)} commas "
            f"(embed_repealed={self._embed_repealed})"
        )
        context.put(_EMBEDDABLE_ARTICLE_COMMAS_KEY, result)

    def _should_embed(self, comma: EmbeddableArticleComma) -> bool:
        return not (comma.is_repealed and not self._embed_repealed)

    def get_required_keys(self) -> set[str]:
        """Requires `embeddable_article_commas` as input."""
        return {_EMBEDDABLE_ARTICLE_COMMAS_KEY}

    def get_produced_keys(self) -> set[str]:
        """Re-declares `embeddable_article_commas`: updates commas with embedding assigned.

        Note: FlowValidator emits a benign WARNING 'Produced key overwrites
        an already available key' — expected and non-blocking.
        """
        return {_EMBEDDABLE_ARTICLE_COMMAS_KEY}
