from commons.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizModel


class EmbeddableQuizQuestionMapper:
    """Converte `EmbeddableQuizModel` in `QuizQuestion` (entità DB).

    Scarta `image_description` (non persistita), mantiene `embedding`.
    """

    @staticmethod
    def to_entity(embeddable: EmbeddableQuizModel) -> QuizQuestion:
        """Mappa un `EmbeddableQuizModel` nell'entità `QuizQuestion`."""
        return QuizQuestion(
            number=embeddable.number,
            question_id=embeddable.question_id,
            topic=embeddable.topic,
            text=embeddable.text,
            correct_answer=embeddable.correct_answer,
            image_filename=embeddable.image_filename,
            embedding=embeddable.embedding,
        )
