from pydantic import BaseModel

from .quiz_metadata import QuizMetadata


class EmbeddedQuizModel(BaseModel):
    """Quiz bank sub-question, ready to be turned into embedding-variant rows.

    Contains `image_description` (not persisted in DB). Embeddings are no longer
    carried on this model at all: `EmbedQuizVariants` computes one embedding per
    (question, variant) pair directly from this model's fields, producing
    `EmbeddableQuizVariant` rows instead.
    """

    number: str
    question_id: int
    topic: str
    text: str
    correct_answer: bool
    image_filename: str | None = None
    image_description: str | None = None
    quiz_metadata: QuizMetadata | None = None
