"""The check UseCase's input, distinct from the wire-format request schema."""

from pydantic import BaseModel, ConfigDict


class QuizAnswerCheckRequest(BaseModel):
    """The question identity, the answer, and the caller's identity (spec 0016, FR-5).

    Not the same type as `api/schemas/quiz_check.py::QuizCheckRequest`: that one is
    the wire-format request body. This one is `QuizAnswerChecker`'s `UseCase` input,
    assembled by the router from the path, the body, and the resolved `UserEntity`.
    """

    model_config = ConfigDict(frozen=True)

    number: str
    submitted_answer: bool
    session_id: str
    telegram_user_id: int
