"""A session's results: totals, a per-topic breakdown and its wrong questions."""

from pydantic import BaseModel, ConfigDict

from .topic_summary import TopicSummary
from .wrong_question import WrongQuestion


class SessionSummary(BaseModel):
    """What a session answered, how well, and what is worth reviewing (spec 0016, FR-9, AD-16).

    `answered`/`correct` are the sums of `by_topic`, kept as their own fields so a caller
    that only wants the totals need not add them up. `by_topic` is ordered by topic name;
    `wrong_questions` lists each wrongly answered question once, in the order it was first
    answered wrongly.
    """

    model_config = ConfigDict(frozen=True)

    answered: int
    correct: int
    by_topic: list[TopicSummary]
    wrong_questions: list[WrongQuestion]
