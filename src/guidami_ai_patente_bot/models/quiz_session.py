"""Per-chat state kept in `context.user_data` for the process lifetime (AD-2)."""

from pydantic import BaseModel, ConfigDict


class QuizSession(BaseModel):
    """The seeded permutation position and the question currently on screen.

    `current_question_number` is what a stale button tap is compared against (FR-3).
    """

    model_config = ConfigDict(frozen=True)

    seed: str
    index: int
    current_question_number: str
