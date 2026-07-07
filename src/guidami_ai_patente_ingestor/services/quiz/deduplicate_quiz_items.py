import logging
from typing import Protocol

from commons.use_cases import UseCase
from commons.utils import deduplicate

logger = logging.getLogger(__name__)


class _QuizItemLike(Protocol):
    """Contratto strutturale minimo per la deduplicazione di un quiz item flat.

    Soddisfatto strutturalmente da `CleanedQuizModel` e `EnrichedQuizModel`
    (nessuna ereditarietà esplicita).
    """

    text: str
    correct_answer: bool
    image: str | None
    number: str


class DeduplicateQuizItems[T: _QuizItemLike](UseCase[list[T], list[T]]):
    """Deduplica una lista flat di quiz item sulla tripla (testo, risposta, immagine).

    Un duplicato esatto è identificato da (testo normalizzato, risposta
    corretta, identità immagine). Generico e Protocol-typed: condiviso da
    `build_quiz_cleaning_flow` (`CleanedQuizModel`) e `build_quiz_indexing_flow`
    (`EnrichedQuizModel`), senza subclassing model-specific.
    """

    def execute(self, request: list[T]) -> list[T]:
        """Deduplica la lista mantenendo il primo item incontrato per ogni chiave.

        Args:
            request: Lista flat di quiz item, potenzialmente con duplicati esatti.

        Returns:
            Lista deduplicata, nello stesso ordine.
        """
        return list(
            deduplicate(
                request,
                key=self._dedup_key,
                on_duplicate=self._log_duplicate,
            )
        )

    @staticmethod
    def _dedup_key(item: _QuizItemLike) -> tuple[str, bool, str | None]:
        """Chiave di unicità: testo normalizzato, risposta corretta, immagine."""
        return item.text.strip(), item.correct_answer, item.image

    @staticmethod
    def _log_duplicate(item: _QuizItemLike) -> None:
        """Logga lo scarto di un quiz item duplicato."""
        logger.warning("skipping duplicate quiz item %s", item.number)
