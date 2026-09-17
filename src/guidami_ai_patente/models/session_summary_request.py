"""SessionSummaryService's UseCase input (spec 0016, FR-9, AD-16)."""

from pydantic import BaseModel, ConfigDict


class SessionSummaryRequest(BaseModel):
    """The caller's identity and the session to summarize."""

    model_config = ConfigDict(frozen=True)

    telegram_user_id: int
    session_id: str
