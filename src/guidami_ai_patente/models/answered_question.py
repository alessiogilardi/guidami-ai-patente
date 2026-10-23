"""One answer a user gave, as read back for mastery computation."""

from pydantic import BaseModel, ConfigDict


class AnsweredQuestion(BaseModel):
    """A recorded answer: question, topic, session, and whether it was correct."""

    model_config = ConfigDict(frozen=True)

    number: str
    topic: str
    session_id: str
    is_correct: bool
