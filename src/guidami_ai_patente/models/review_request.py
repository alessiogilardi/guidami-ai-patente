"""Input of the review-session use case."""

from pydantic import BaseModel, ConfigDict


class ReviewRequest(BaseModel):
    """Identifies the user and the session a review is requested for."""

    model_config = ConfigDict(frozen=True)

    telegram_user_id: int
    session_id: str
