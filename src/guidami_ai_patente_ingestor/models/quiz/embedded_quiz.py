from pydantic import BaseModel

from .quiz_metadata import QuizMetadata


class EmbeddedQuizModel(BaseModel):
    """Quiz bank sub-question carrying the computed embedding.

    Contains `image_description` (not persisted in DB). The embedding is
    computed from `quiz_metadata` directly (`QuizMetadata` is itself
    `Embeddable`), not from a delegated property on this model.
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
