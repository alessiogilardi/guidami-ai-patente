import logging
from collections.abc import Iterable

from commons.ai.embedding import EmbeddingService
from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.models.quiz.embeddable_quiz import EmbeddableQuizModel

logger = logging.getLogger(__name__)


class EmbedQuizMetadata(UseCase[Iterable[EmbeddableQuizModel], list[EmbeddableQuizModel]]):
    """Computes the embedding of every item that carries `quiz_metadata`.

    Items with metadata are passed to `EmbeddingService` (they satisfy `Embeddable`
    via their `embedded_text`, which delegates to `quiz_metadata`). Items without
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
        to_embed = [item for item in items if item.quiz_metadata is not None]
        if not to_embed:
            return items

        try:
            # TODO: narrow to EmbeddingError once the domain-exception pattern lands
            # (see the deferred plan); a broad catch here also swallows real bugs.
            vectors = self._embedding_service.execute(to_embed)
        except Exception:
            logger.warning("metadata embedding failed, skipping batch")
            return items

        # EmbeddingService returns vectors aligned 1:1 to `to_embed`; consuming them
        # in lockstep while re-scanning `items` avoids tracking positional indices.
        vectors_iter = iter(vectors)
        result: list[EmbeddableQuizModel] = []
        for item in items:
            if item.quiz_metadata is None:
                result.append(item)
            else:
                result.append(item.model_copy(update={"embedding": next(vectors_iter)}))
        return result
