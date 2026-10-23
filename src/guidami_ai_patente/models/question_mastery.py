"""Mastery state of one question for one user."""

from pydantic import BaseModel, ConfigDict


class QuestionMastery(BaseModel):
    """Wrong-answer count, current correct streak and review status of a question."""

    model_config = ConfigDict(frozen=True)

    number: str
    topic: str
    wrong_count: int
    streak: int
    in_review: bool

    @property
    def mastered(self) -> bool:
        """Whether the question is mastered, i.e. no longer in review."""
        return not self.in_review
