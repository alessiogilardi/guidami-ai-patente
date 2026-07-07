from collections.abc import Iterator
from typing import NamedTuple

from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.mappers import QuizMapper
from guidami_ai_patente_ingestor.models.quiz import (
    CleanedQuizModel,
    ParsedQuizItemModel,
    ParsedQuizModel,
)


class _FlatEntry(NamedTuple):
    """Coppia (sotto-domanda, domanda padre) prodotta in fase di appiattimento."""

    sub_question: ParsedQuizItemModel
    main_question: ParsedQuizModel


class FlattenQuiz(UseCase[list[ParsedQuizModel], list[CleanedQuizModel]]):
    """Appiattisce il quiz bank parsed (nested) in cleaned (flat).

    Per ogni coppia (sotto-domanda, domanda padre) delega a
    `QuizMapper.from_parsed_to_cleaned`. Non deduplica: la deduplicazione è
    un transform separato (`DeduplicateQuizItems`), incatenato dopo questo
    step in `build_quiz_cleaning_flow`.
    """

    def execute(self, request: list[ParsedQuizModel]) -> list[CleanedQuizModel]:
        """Appiattisce il quiz bank.

        Args:
            request: Lista di domande parsed con sotto-domande annidate.

        Returns:
            Lista piatta di `CleanedQuizModel`.
        """
        return [
            QuizMapper.from_parsed_to_cleaned(entry.sub_question, entry.main_question)
            for entry in self._flatten(request)
        ]

    @staticmethod
    def _flatten(questions: list[ParsedQuizModel]) -> Iterator[_FlatEntry]:
        """Appiattisce le domande annidate in coppie (sotto-domanda, domanda padre)."""
        return (
            _FlatEntry(sub_question=sub_q, main_question=main_q)
            for main_q in questions
            for sub_q in main_q.sub_questions
        )
