from pydantic import BaseModel

from .quiz_metadata import QuizMetadata


class QuizQuestion(BaseModel):
    """Row of the `quiz_questions` table (see db/init.sql)."""

    number: str
    question_id: int
    topic: str
    text: str
    correct_answer: bool
    image_filename: str | None = None
    embedding: list[float] | None = None
    quiz_metadata: QuizMetadata | None = None
