import logging
from collections.abc import Sequence
from itertools import batched

from commons.ai.embedding.clients import EmbeddingClient
from commons.observability import ItemProgressReporter, NullProgressReporter, tracker
from commons.use_cases import UseCase

logger = logging.getLogger(__name__)


class EmbeddingService(UseCase[Sequence[str], list[list[float]]]):
    """Computes embeddings for a sequence of texts in batches.

    Pure: returns a new list of vectors, aligned 1:1 to the input texts (same order).
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

    def execute(self, request: Sequence[str]) -> list[list[float]]:
        """Returns the vectors aligned to `texts` (same order). No mutation."""
        batches = list(batched(request, self._batch_size))
        vectors: list[list[float]] = []
        tracked_batches = tracker(self._progress, "batches", batches)
        for batch_number, batch in enumerate(tracked_batches, start=1):
            logger.info("embedding batch %d/%d (%d items)", batch_number, len(batches), len(batch))
            vectors.extend(self._client.embed_passages(list(batch)))
        return vectors
