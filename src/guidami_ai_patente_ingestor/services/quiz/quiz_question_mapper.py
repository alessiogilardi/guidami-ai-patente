import logging
from pathlib import PurePosixPath

from commons.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.entities import QuizMainQuestion

logger = logging.getLogger(__name__)


class QuizQuestionMapper:
    """Appiattisce le domande madri del quiz bank in righe `QuizQuestion`, deduplicando."""

    def map(self, main_questions: list[QuizMainQuestion]) -> list[QuizQuestion]:
        """Genera una `QuizQuestion` per sotto-domanda, scartando i duplicati esatti.

        Un duplicato esatto è identificato dalla tripla (testo normalizzato,
        risposta corretta, identità immagine).
        """
        questions: list[QuizQuestion] = []
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

                questions.append(
                    QuizQuestion(
                        number=sub_question.number,
                        question_id=main_question.question_id,
                        topic=main_question.topic,
                        text=text,
                        correct_answer=sub_question.correct_answer,
                        image_filename=self._image_filename(sub_question.image),
                    )
                )

        return questions

    def _image_filename(self, image: str | None) -> str | None:
        return PurePosixPath(image).name if image is not None else None
