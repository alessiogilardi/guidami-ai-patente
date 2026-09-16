"""The question projection the bot receives from `GET /quiz-questions/random`."""

from pydantic import BaseModel, ConfigDict


class QuizQuestion(BaseModel):
    """A quiz question as served by the API (FR-1).

    Field-for-field mirror of `guidami_ai_patente`'s `QuizQuestionResponse`: the
    bot's only coupling to that shape is the HTTP wire contract (AD-1), so this is
    declared independently rather than imported.
    """

    model_config = ConfigDict(frozen=True)

    number: str
    topic: str
    text: str
    image_url: str | None
