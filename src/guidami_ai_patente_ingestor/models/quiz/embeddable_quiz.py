from pydantic import BaseModel

from domain.entities.quiz import QuizMetadata


class EmbeddableQuizModel(BaseModel):
    """Modello intermedio per il calcolo dell'embedding di una sotto-domanda.

    Contiene `image_description` (non persistita in DB) e `embedded_text`, che
    delega a `quiz_metadata.embedded_text`.
    """

    number: str
    question_id: int
    topic: str
    text: str
    correct_answer: bool
    image_filename: str | None = None
    image_description: str | None = None
    embedding: list[float] | None = None
    quiz_metadata: QuizMetadata | None = None

    @property
    def embedded_text(self) -> str:
        """Testo usato per il calcolo dell'embedding, delegato a `quiz_metadata`.

        Richiede `quiz_metadata is not None`: `EmbedQuizMetadata` filtra gli item
        senza metadata prima di leggere questa property.
        """
        return self.quiz_metadata.embedded_text  # type: ignore[union-attr]
