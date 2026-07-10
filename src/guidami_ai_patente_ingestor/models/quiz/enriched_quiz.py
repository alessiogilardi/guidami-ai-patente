from pydantic import BaseModel

from domain.entities.quiz import QuizMetadata


class EnrichedQuizModel(BaseModel):
    """Enriched quiz bank sub-question, flattened, with inline `image_description`."""

    question_id: int
    topic: str
    number: str
    text: str
    correct_answer: bool
    image: str | None = None
    image_description: str | None = None
    quiz_metadata: QuizMetadata | None = None
