from commons.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizQuestion


class EmbeddableQuizQuestionMapper:
    """Converte `EmbeddableQuizQuestion` in `QuizQuestion` (entità DB).

    Scarta `image_description` (non persistita), mantiene `embedding`.
    """

    @staticmethod
    def to_entity(embeddable: EmbeddableQuizQuestion) -> QuizQuestion:
        """Mappa un `EmbeddableQuizQuestion` nell'entità `QuizQuestion`."""
        return QuizQuestion(
            number=embeddable.number,
            question_id=embeddable.question_id,
            topic=embeddable.topic,
            text=embeddable.text,
            correct_answer=embeddable.correct_answer,
            image_filename=embeddable.image_filename,
            embedding=embeddable.embedding,
        )
