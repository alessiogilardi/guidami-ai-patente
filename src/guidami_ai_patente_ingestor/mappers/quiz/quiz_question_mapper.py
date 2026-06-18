import logging
from pathlib import PurePosixPath

from guidami_ai_patente_ingestor.models.quiz import (
    EmbeddableQuizQuestion,
    EnrichedQuizMainQuestion,
    EnrichedQuizSubQuestion,
)

logger = logging.getLogger(__name__)


class QuizQuestionMapper:
    """Trasforma il quiz bank enriched in `EmbeddableQuizQuestion`.

    Tutti i metodi sono statici: la classe è priva di stato e di dipendenze iniettate.
    """

    @staticmethod
    def from_enriched_quiz_sub_question_to_embeddable_quiz_question(
        sub: EnrichedQuizSubQuestion,
        parent: EnrichedQuizMainQuestion,
    ) -> EmbeddableQuizQuestion:
        """Mappa una sotto-domanda enriched in `EmbeddableQuizQuestion`.

        Args:
            sub: La sotto-domanda da mappare.
            parent: La domanda madre che fornisce `question_id` e `topic`.

        Returns:
            `EmbeddableQuizQuestion` pronto per il calcolo dell'embedding.
        """
        return EmbeddableQuizQuestion(
            number=sub.number,
            question_id=parent.question_id,
            topic=parent.topic,
            text=sub.text.strip(),
            correct_answer=sub.correct_answer,
            image_filename=QuizQuestionMapper._image_filename(sub.image),
            image_description=sub.image_description,
        )

    @staticmethod
    def from_enriched_quiz_main_questions_to_embeddable_quiz_questions(
        main_questions: list[EnrichedQuizMainQuestion],
    ) -> list[EmbeddableQuizQuestion]:
        """Appiattisce le domande madri in `EmbeddableQuizQuestion`, deduplicando.

        Un duplicato esatto è identificato dalla tripla (testo normalizzato,
        risposta corretta, identità immagine).

        Args:
            main_questions: Domande madri del quiz bank enriched.

        Returns:
            Lista di `EmbeddableQuizQuestion` deduplicata, pronta per l'embedding.
        """
        questions: list[EmbeddableQuizQuestion] = []
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
                    QuizQuestionMapper.from_enriched_quiz_sub_question_to_embeddable_quiz_question(
                        sub_question, main_question
                    )
                )

        return questions

    @staticmethod
    def _image_filename(image: str | None) -> str | None:
        return PurePosixPath(image).name if image is not None else None
