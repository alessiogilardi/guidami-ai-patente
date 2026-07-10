import logging
from collections.abc import Iterable

from commons.services.embeddings import EmbeddingService
from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.models.quiz.embeddable_quiz import EmbeddableQuizModel

logger = logging.getLogger(__name__)


class EmbedQuizMetadata(UseCase[Iterable[EmbeddableQuizModel], list[EmbeddableQuizModel]]):
    """Computes the embedding of every item from its `quiz_metadata`.

    Filters items with `quiz_metadata is not None` and passes them to `EmbeddingService`
    (they satisfy `Embeddable` via `quiz_metadata.embedded_text`). Items without
    metadata pass through unchanged with `embedding = None`.
    """

    def __init__(self, embedding_service: EmbeddingService) -> None:
        """Injects the embedding service used to compute the vectors."""
        self._embedding_service = embedding_service

    def execute(self, request: Iterable[EmbeddableQuizModel]) -> list[EmbeddableQuizModel]:
        """Assigns the embedding to items with metadata; leaves the others unchanged.

        Args:
            request: Iterable of embeddable items, some with `quiz_metadata is None`.

        Returns:
            List with `embedding` populated for items with metadata. If the computation
            fails, returns the original list unchanged with a warning logged.
        """
        items = list(request)
        to_embed = [
            (i, item.quiz_metadata)
            for i, item in enumerate(items)
            if item.quiz_metadata is not None
        ]
        if not to_embed:
            return items

        try:
            vectors = self._embedding_service.execute([metadata for _, metadata in to_embed])
        except Exception:
            logger.warning("metadata embedding failed, skipping batch")
            return items

        result = list(items)
        for (i, _), vector in zip(to_embed, vectors, strict=True):
            result[i] = result[i].model_copy(update={"embedding": vector})
        return result
