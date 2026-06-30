import logging
from typing import cast

from commons.services.embeddings import Embedded, EmbeddingService
from flowstep import FlowContext, Step

logger = logging.getLogger(__name__)


class EmbedStep(Step):
    """Step generico: assegna l'embedding agli item presenti nel context (in place)."""

    def __init__(self, name: str, embedding_service: EmbeddingService, items_key: str) -> None:
        """Inietta il service di embedding e la chiave context degli item da embeddare."""
        super().__init__(name)
        self._embed = embedding_service
        self._items_key = items_key

    def execute(self, context: FlowContext) -> None:
        """Legge gli item da `items_key`, assegna gli embedding, ri-scrive `items_key`."""
        items = cast(list[Embedded], context.get(self._items_key))
        vectors = self._embed(items)
        for item, vector in zip(items, vectors, strict=True):
            item.embedding = vector
        context.put(self._items_key, items)

    def get_required_keys(self) -> set[str]:
        """Ritorna `{items_key}`: lo step richiede gli item nel context."""
        return {self._items_key}

    def get_produced_keys(self) -> set[str]:
        """Ritorna `{items_key}`: lo step ri-scrive gli item arricchiti."""
        return {self._items_key}
