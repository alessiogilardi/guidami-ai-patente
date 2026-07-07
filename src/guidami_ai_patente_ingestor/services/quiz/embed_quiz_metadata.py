import logging

from commons.services.embeddings import EmbeddingService
from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.models.quiz.embeddable_quiz import EmbeddableQuizModel

logger = logging.getLogger(__name__)


class EmbedQuizMetadata(UseCase[list[EmbeddableQuizModel], list[EmbeddableQuizModel]]):
    """Calcola l'embedding di ogni item dal relativo `quiz_metadata`.

    Filtra gli item con `quiz_metadata is not None` e li passa a `EmbeddingService`
    (soddisfano `Embeddable` via `quiz_metadata.embedded_text`). Gli item senza
    metadata transitano invariati con `embedding = None`.
    """

    def __init__(self, embedding_service: EmbeddingService) -> None:
        """Inietta il service di embedding usato per calcolare i vettori."""
        self._embedding_service = embedding_service

    def execute(self, request: list[EmbeddableQuizModel]) -> list[EmbeddableQuizModel]:
        """Assegna l'embedding agli item con metadata; lascia invariati gli altri.

        Args:
            request: Lista di item embeddable, alcuni con `quiz_metadata is None`.

        Returns:
            Lista con `embedding` popolato per gli item con metadata. Se il calcolo
            fallisce, ritorna la lista originale invariata con un warning loggato.
        """
        to_embed = [
            (i, item.quiz_metadata)
            for i, item in enumerate(request)
            if item.quiz_metadata is not None
        ]
        if not to_embed:
            return request

        try:
            vectors = self._embedding_service.execute([metadata for _, metadata in to_embed])
        except Exception:
            logger.warning("metadata embedding failed, skipping batch")
            return request

        result = list(request)
        for (i, _), vector in zip(to_embed, vectors, strict=True):
            result[i] = result[i].model_copy(update={"embedding": vector})
        return result
