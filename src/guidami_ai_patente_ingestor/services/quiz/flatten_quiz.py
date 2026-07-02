import logging
from collections.abc import Iterator
from typing import NamedTuple

from commons.use_cases import UseCase
from commons.utils import deduplicate
from guidami_ai_patente_ingestor.mappers import QuizMapper
from guidami_ai_patente_ingestor.models.quiz import (
    CleanedQuizModel,
    ParsedQuizItemModel,
    ParsedQuizModel,
)

logger = logging.getLogger(__name__)


class _FlatEntry(NamedTuple):
    """Coppia (sotto-domanda, domanda padre) prodotta in fase di appiattimento."""

    sub_question: ParsedQuizItemModel
    main_question: ParsedQuizModel


class FlattenQuiz(UseCase[list[ParsedQuizModel], list[CleanedQuizModel]]):
    """Appiattisce e deduplica il quiz bank parsed (nested) in cleaned (flat).

    Un duplicato esatto è identificato dalla tripla (testo normalizzato,
    risposta corretta, identità immagine). Per ogni item mantenuto delega a
    `QuizMapper.from_parsed_to_cleaned`.
    """

    def execute(self, request: list[ParsedQuizModel]) -> list[CleanedQuizModel]:
        """Appiattisce e deduplica il quiz bank.

        Args:
            request: Lista di domande parsed con sotto-domande annidate.

        Returns:
            Lista piatta e deduplicata di `CleanedQuizModel`.
        """
        flat_entries = self._flatten(request)
        unique_entries = deduplicate(
            flat_entries,
            key=self._dedup_key,
            on_duplicate=self._log_duplicate,
        )
        return [
            QuizMapper.from_parsed_to_cleaned(entry.sub_question, entry.main_question)
            for entry in unique_entries
        ]

    @staticmethod
    def _flatten(questions: list[ParsedQuizModel]) -> Iterator[_FlatEntry]:
        """Appiattisce le domande annidate in coppie (sotto-domanda, domanda padre)."""
        return (
            _FlatEntry(sub_question=sub_q, main_question=main_q)
            for main_q in questions
            for sub_q in main_q.sub_questions
        )

    @staticmethod
    def _dedup_key(entry: _FlatEntry) -> tuple[str, bool, str | None]:
        """Chiave di unicità: testo normalizzato, risposta corretta, immagine."""
        sub_question = entry.sub_question
        return sub_question.text.strip(), sub_question.correct_answer, sub_question.image

    @staticmethod
    def _log_duplicate(entry: _FlatEntry) -> None:
        """Logga lo scarto di una sotto-domanda duplicata."""
        logger.warning(
            "skipping duplicate sub-question %s (question_id=%d)",
            entry.sub_question.number,
            entry.main_question.question_id,
        )
