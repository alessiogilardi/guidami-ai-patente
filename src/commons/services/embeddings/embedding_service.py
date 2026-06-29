import logging
from collections.abc import Sequence

from commons.clients import EmbeddingClient

from .protocols import Embeddable

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Calcola gli embedding di una sequenza di Embeddable in batch.

    Puro: non muta gli item in input. Ritorna i vettori allineati 1:1 (stesso ordine).
    """

    def __init__(self, client: EmbeddingClient, batch_size: int) -> None:
        """Inietta il client di embedding e la dimensione del batch (>= 1)."""
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        self._client = client
        self._batch_size = batch_size

    def embed(self, items: Sequence[Embeddable]) -> list[list[float]]:
        """Ritorna i vettori allineati a `items` (stesso ordine). Nessuna mutazione."""
        total_batches = -(-len(items) // self._batch_size)
        vectors: list[list[float]] = []
        for start in range(0, len(items), self._batch_size):
            batch = items[start : start + self._batch_size]
            batch_number = start // self._batch_size + 1
            logger.info(f"embedding batch {batch_number}/{total_batches} ({len(batch)} items)")
            vectors.extend(self._client.embed_passages([item.embedded_text for item in batch]))
        return vectors
