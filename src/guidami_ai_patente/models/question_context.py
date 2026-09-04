"""Exactly the question data the explanation writer is allowed to see."""

from pydantic import BaseModel, ConfigDict


class QuestionContext(BaseModel):
    """The question as the writer receives it (FR-10).

    Three fields, deliberately: the text, the verdict to justify, and the image
    description when the question has one. Not `QuizQuestionSummary`, which is the
    *client*-facing projection and carries `image_filename` (a content hash the model
    has no use for) while omitting the description; and not `QuizEvaluationRow`, which
    carries a 1536-float query vector the cached path never needs.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    correct_answer: bool
    image_description: str | None
