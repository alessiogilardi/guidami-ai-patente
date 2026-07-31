import logging
from collections.abc import Sequence

from commons.ai.embedding.clients import EmbeddingClient
from commons.observability import ItemProgressReporter, NullProgressReporter
from commons.use_cases import UseCase

from .protocols import Embeddable

logger = logging.getLogger(__name__)


class EmbeddingService(UseCase[Sequence[Embeddable], list[list[float]]]):
    """Computes embeddings for a sequence of Embeddable items in batches.

    Pure: does not mutate the input items. Returns vectors aligned 1:1 (same order).
    """

    def __init__(
        self,
        batch_size: int,
        client: EmbeddingClient,
        progress: ItemProgressReporter | None = None,
    ) -> None:
        """Injects the batch size (>= 1), the embedding client, and an optional reporter.

        Args:
            batch_size: Number of items embedded per call to `client`. Must be >= 1.
            client: Client computing embeddings for a batch of texts.
            progress: Optional port reporting one tick per completed batch. When
                `None`, defaults to `NullProgressReporter`, a no-op collaborator.
        """
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        self._client = client
        self._batch_size = batch_size
        self._progress: ItemProgressReporter = (
            progress if progress is not None else NullProgressReporter()
        )

    def execute(self, request: Sequence[Embeddable]) -> list[list[float]]:
        """Returns the vectors aligned to `items` (same order). No mutation."""
        total_batches = self._get_total_batches(request)
        vectors: list[list[float]] = []
        self._progress.begin_items("batches", total_batches)
        try:
            for start in range(0, len(request), self._batch_size):
                vectors.extend(self._embed(request, start=start, total_batches=total_batches))
                self._progress.advance_item()
        finally:
            self._progress.end_items()
        return vectors

    def _embed(
        self, request: Sequence[Embeddable], *, start: int, total_batches: int
    ) -> list[list[float]]:
        batch = request[start : start + self._batch_size]
        batch_number = start // self._batch_size + 1
        logger.info(f"embedding batch {batch_number}/{total_batches} ({len(batch)} items)")
        return self._client.embed_passages([item.embedded_text for item in batch])

    def _get_total_batches(self, request: Sequence[Embeddable]) -> int:
        return -(-len(request) // self._batch_size)
