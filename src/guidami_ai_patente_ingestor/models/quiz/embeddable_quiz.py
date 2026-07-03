from pydantic import BaseModel

from domain.entities.quiz import QuizMetadata


class EmbeddableQuizModel(BaseModel):
    """Modello intermedio per il calcolo dell'embedding di una sotto-domanda.

    Contiene `image_description` (non persistita in DB) e `embedded_text`
    che include la descrizione dell'immagine quando presente.
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
        """Testo usato per il calcolo dell'embedding, con descrizione immagine se presente."""
        base = f"{self.topic} {self.text}"
        return f"{base} {self.image_description}" if self.image_description else base
