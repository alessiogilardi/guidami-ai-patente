from pydantic import BaseModel

from domain.entities.quiz import QuizMetadata


class EnrichedQuizModel(BaseModel):
    """Sotto-domanda del quiz bank enriched, appiattita, con `image_description` inline."""

    question_id: int
    topic: str
    number: str
    text: str
    correct_answer: bool
    image: str | None = None
    image_description: str | None = None
    quiz_metadata: QuizMetadata | None = None
