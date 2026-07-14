import logging
from collections.abc import Sequence

from commons.ai.embedding.clients import EmbeddingClient
from commons.use_cases import UseCase

from .protocols import Embeddable

logger = logging.getLogger(__name__)


class EmbeddingService(UseCase[Sequence[Embeddable], list[list[float]]]):
    """Computes embeddings for a sequence of Embeddable items in batches.

    Pure: does not mutate the input items. Returns vectors aligned 1:1 (same order).
    """

    def __init__(self, batch_size: int, client: EmbeddingClient) -> None:
        """Injects the batch size (>= 1) and the embedding client."""
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        self._client = client
        self._batch_size = batch_size

    def execute(self, request: Sequence[Embeddable]) -> list[list[float]]:
        """Returns the vectors aligned to `items` (same order). No mutation."""
        total_batches = -(-len(request) // self._batch_size)
        vectors: list[list[float]] = []
        for start in range(0, len(request), self._batch_size):
            batch = request[start : start + self._batch_size]
            batch_number = start // self._batch_size + 1
            logger.info(f"embedding batch {batch_number}/{total_batches} ({len(batch)} items)")
            vectors.extend(self._client.embed_passages([item.embedded_text for item in batch]))
        return vectors
