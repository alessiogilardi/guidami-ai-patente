"""A wrongly answered question the session summary lists (spec 0016, FR-9)."""

from pydantic import BaseModel, ConfigDict


class WrongQuestion(BaseModel):
    """The number and text of a question answered wrongly at least once in the session.

    Field-for-field mirror of the backend's own `WrongQuestionResponse`: declared
    independently, same posture as `SessionSummary` (AD-1).
    """

    model_config = ConfigDict(frozen=True)

    number: str
    text: str
