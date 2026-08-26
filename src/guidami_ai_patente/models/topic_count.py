"""One row of the topics listing."""

from pydantic import BaseModel, ConfigDict


class TopicCount(BaseModel):
    """A distinct `quiz_questions.topic` and how many questions carry it (FR-16)."""

    model_config = ConfigDict(frozen=True)

    topic: str
    question_count: int
