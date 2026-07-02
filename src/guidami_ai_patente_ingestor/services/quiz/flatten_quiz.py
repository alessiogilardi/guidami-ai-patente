import logging

from commons.use_cases import UseCase
from commons.utils import deduplicate
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
        pairs = ((sub_q, main_q) for main_q in request for sub_q in main_q.sub_questions)
        return [
            QuizMapper.from_parsed_to_cleaned(sub_q, main_q)
            for sub_q, main_q in deduplicate(
                pairs,
                key=lambda p: (p[0].text.strip(), p[0].correct_answer, p[0].image),
                on_duplicate=lambda p: logger.warning(
                    "skipping duplicate sub-question %s (question_id=%d)",
                    p[0].number,
                    p[1].question_id,
                ),
            )
        ]
