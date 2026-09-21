"""A question a session answered wrongly, as its summary lists it."""

from pydantic import BaseModel, ConfigDict


class WrongQuestion(BaseModel):
    """The number and text of a question answered wrongly at least once in a session.

    `correct_answer` is absent by construction, like `QuizQuestionSummary`: the summary
    tells the user what to review, never what the right answer was.
    """

    model_config = ConfigDict(frozen=True)

    number: str
    text: str
