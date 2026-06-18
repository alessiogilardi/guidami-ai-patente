from pydantic import BaseModel


class QuizQuestion(BaseModel):
    """Riga della tabella `quiz_questions` (vedi db/init.sql)."""

    number: str
    question_id: int
    topic: str
    text: str
    correct_answer: bool
    image_filename: str | None = None
    embedding: list[float] | None = None

    @property
    def embedded_text(self) -> str:
        """Testo usato per il calcolo dell'embedding (topic + testo)."""
        return f"{self.topic} {self.text}"
