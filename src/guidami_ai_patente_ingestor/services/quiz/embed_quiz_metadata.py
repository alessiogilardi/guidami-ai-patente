import logging
from collections.abc import Iterable

from commons.ai.embedding import EmbeddingService
from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.models.quiz import EmbeddedQuizModel, QuizMetadata

logger = logging.getLogger(__name__)


class EmbedQuizMetadata(UseCase[Iterable[EmbeddedQuizModel], list[EmbeddedQuizModel]]):
    """Computes the embedding of every item that carries `quiz_metadata`.

    Items with metadata have their `quiz_metadata` passed directly to `EmbeddingService`.
    Items without metadata pass through unchanged with `embedding = None`.
    """

    def __init__(self, embedding_service: EmbeddingService) -> None:
        """Injects the embedding service used to compute the vectors."""
        self._embedding_service = embedding_service

    def execute(self, request: Iterable[EmbeddedQuizModel]) -> list[EmbeddedQuizModel]:
        """Assigns the embedding to items with metadata; leaves the others unchanged.

        Args:
            request: Iterable of embedded-model items, some with `quiz_metadata is None`.

        Returns:
            List with `embedding` populated for items with metadata. If the computation
            fails, returns the original list unchanged with a warning logged.
        """
        items = list(request)
        metadata_to_embed = self._get_to_embed(items)

        if not metadata_to_embed:
            return items
        vectors = self._embed(metadata_to_embed)

        if not vectors:
            return items

        return self._apply_embeddings(items, vectors)

    def _get_to_embed(self, request: list[EmbeddedQuizModel]) -> list[QuizMetadata]:
        return [item.quiz_metadata for item in request if item.quiz_metadata is not None]

    def _embed(self, metadata_list: list[QuizMetadata]) -> list[list[float]] | None:
        """Fetches embeddings from the service, safely handling exceptions."""
        try:
            # TODO: narrow to EmbeddingError once the domain-exception pattern lands
            return self._embedding_service(metadata_list)
        except Exception as e:
            logger.warning(f"Metadata embedding failed, skipping batch. Error: {e}")
            return None

    def _apply_embeddings(
        self, items: list[EmbeddedQuizModel], vectors: list[list[float]]
    ) -> list[EmbeddedQuizModel]:
        """Merges the computed vectors back into the original items."""
        vectors_iter = iter(vectors)

        return [
            item.model_copy(update={"embedding": next(vectors_iter)})
            if item.quiz_metadata is not None
            else item
            for item in items
        ]
