import logging

from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.mappers.quiz_mapper import QuizMapper
from guidami_ai_patente_ingestor.models.quiz.cleaned_quiz import CleanedQuizModel
from guidami_ai_patente_ingestor.models.quiz.parsed_quiz import ParsedQuizModel

logger = logging.getLogger(__name__)


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
        cleaned: list[CleanedQuizModel] = []
        seen: set[tuple[str, bool, str | None]] = set()

        for main_question in request:
            for sub_question in main_question.sub_questions:
                text = sub_question.text.strip()
                key = (text, sub_question.correct_answer, sub_question.image)
                if key in seen:
                    logger.warning(
                        "skipping duplicate sub-question %s (question_id=%d)",
                        sub_question.number,
                        main_question.question_id,
                    )
                    continue
                seen.add(key)
                cleaned.append(QuizMapper.from_parsed_to_cleaned(sub_question, main_question))

        return cleaned
