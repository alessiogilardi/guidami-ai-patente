from pydantic import BaseModel


class CleanedQuizModel(BaseModel):
    """Sotto-domanda del quiz bank, appiattita e deduplicata, auto-contenuta."""

    question_id: int
    topic: str
    number: str
    text: str
    correct_answer: bool
    image: str | None = None
