import logging
from collections.abc import Iterable
from typing import Protocol

from commons.use_cases import UseCase
from commons.utils import deduplicate

logger = logging.getLogger(__name__)


class _QuizItemLike(Protocol):
    """Minimal structural contract for deduplicating a flat quiz item.

    Satisfied structurally by `CleanedQuizModel` and `EnrichedQuizModel`
    (no explicit inheritance).
    """

    text: str
    correct_answer: bool
    image: str | None
    number: str


class DeduplicateQuizItems[T: _QuizItemLike](UseCase[Iterable[T], list[T]]):
    """Deduplicates a flat iterable of quiz items on the triple (text, answer, image).

    An exact duplicate is identified by (normalized text, correct answer,
    image identity). Generic and Protocol-typed: shared by
    `build_quiz_cleaning_flow` (`CleanedQuizModel`) and `build_quiz_indexing_flow`
    (`EnrichedQuizModel`), without model-specific subclassing.
    """

    def execute(self, request: Iterable[T]) -> list[T]:
        """Deduplicates, keeping the first item encountered for each key.

        Args:
            request: Flat iterable of quiz items, potentially with exact duplicates.

        Returns:
            Deduplicated list, in the same order.
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
        """Uniqueness key: normalized text, correct answer, image."""
        return item.text.strip(), item.correct_answer, item.image

    @staticmethod
    def _log_duplicate(item: _QuizItemLike) -> None:
        """Logs the discarding of a duplicate quiz item."""
        logger.warning("skipping duplicate quiz item %s", item.number)
