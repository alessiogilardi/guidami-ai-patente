"""The check UseCase's two-field input, distinct from the wire-format request schema."""

from pydantic import BaseModel, ConfigDict


class QuizAnswerCheckRequest(BaseModel):
    """The question identity and the answer submitted for it (spec 0013, FR-4).

    Not the same type as `api/schemas/quiz_check.py::QuizCheckRequest`: that one is
    the wire-format request body (`answer` only, `number` comes from the path). This
    one is `QuizAnswerChecker`'s `UseCase` input, assembled by the router from both.
    """

    model_config = ConfigDict(frozen=True)

    number: str
    submitted_answer: bool
