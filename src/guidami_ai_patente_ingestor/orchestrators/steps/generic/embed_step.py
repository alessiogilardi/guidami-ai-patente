import logging
from typing import cast

from flowstep import FlowContext, Step

from commons.services.embeddings import Embedded, EmbeddingService

logger = logging.getLogger(__name__)


class EmbedStep(Step):
    """Generic step: assigns embeddings to the items present in the context (in place)."""

    def __init__(self, name: str, items_key: str, embedding_service: EmbeddingService) -> None:
        """Injects the items-to-embed context key and the embedding service."""
        super().__init__(name)
        self._embed = embedding_service
        self._items_key = items_key

    def execute(self, context: FlowContext) -> None:
        """Reads items from `items_key`, assigns embeddings, rewrites `items_key`."""
        items = cast(list[Embedded], context.get(self._items_key))
        vectors = self._embed(items)
        for item, vector in zip(items, vectors, strict=True):
            item.embedding = vector
        context.put(self._items_key, items)

    def get_required_keys(self) -> set[str]:
        """Returns `{items_key}`: the step requires the items in the context."""
        return {self._items_key}

    def get_produced_keys(self) -> set[str]:
        """Returns `{items_key}`: the step rewrites the enriched items."""
        return {self._items_key}
