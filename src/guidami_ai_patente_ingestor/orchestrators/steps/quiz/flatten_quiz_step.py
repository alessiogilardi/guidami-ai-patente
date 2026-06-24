"""Step che appiattisce e deduplica il quiz bank parsed (nested) in cleaned (flat)."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.mappers.quiz import QuizMapper
from guidami_ai_patente_ingestor.models.quiz import CleanedQuizModel, ParsedQuizModel
from guidami_ai_patente_ingestor.orchestrators import context_keys

logger = logging.getLogger(__name__)


class FlattenQuizStep(Step):
    """Appiattisce e deduplica il quiz bank parsed (nested) in `CleanedQuizModel` (flat).

    Un duplicato esatto è identificato dalla tripla (testo normalizzato,
    risposta corretta, identità immagine). Per ogni item mantenuto delega a
    `QuizMapper.from_parsed_to_cleaned`.
    """

    def execute(self, context: FlowContext) -> None:
        """Legge `PARSED_QUIZ`, appiattisce+dedup e scrive `CLEANED_QUIZ`.

        Args:
            context: Shared pipeline context.
        """
        main_questions = cast(list[ParsedQuizModel], context.get(context_keys.PARSED_QUIZ))
        cleaned = self._flatten_and_dedup(main_questions)
        logger.info(
            f"Flattened {len(main_questions)} main questions → {len(cleaned)} cleaned questions"
        )
        context.put(context_keys.CLEANED_QUIZ, cleaned)

    def get_required_keys(self) -> set[str]:
        """Richiede `PARSED_QUIZ` in input."""
        return {context_keys.PARSED_QUIZ}

    def get_produced_keys(self) -> set[str]:
        """Produce `CLEANED_QUIZ`."""
        return {context_keys.CLEANED_QUIZ}

    @staticmethod
    def _flatten_and_dedup(main_questions: list[ParsedQuizModel]) -> list[CleanedQuizModel]:
        cleaned: list[CleanedQuizModel] = []
        seen: set[tuple[str, bool, str | None]] = set()

        for main_question in main_questions:
            for sub_question in main_question.sub_questions:
                text = sub_question.text.strip()
                key = (text, sub_question.correct_answer, sub_question.image)
                if key in seen:
                    logger.warning(
                        f"skipping duplicate sub-question {sub_question.number} "
                        f"(question_id={main_question.question_id})"
                    )
                    continue
                seen.add(key)
                cleaned.append(QuizMapper.from_parsed_to_cleaned(sub_question, main_question))

        return cleaned
