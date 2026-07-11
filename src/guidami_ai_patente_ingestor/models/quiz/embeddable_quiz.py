from pydantic import BaseModel

from .quiz_metadata import QuizMetadata


class EmbeddableQuizModel(BaseModel):
    """Intermediate model for computing the embedding of a sub-question.

    Contains `image_description` (not persisted in DB) and `embedded_text`,
    which delegates to `quiz_metadata.embedded_text`.
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
        """Text used for computing the embedding, delegated to `quiz_metadata`.

        Requires `quiz_metadata is not None`: `EmbedQuizMetadata` filters out
        items without metadata before reading this property.
        """
        return self.quiz_metadata.embedded_text  # type: ignore[union-attr]
