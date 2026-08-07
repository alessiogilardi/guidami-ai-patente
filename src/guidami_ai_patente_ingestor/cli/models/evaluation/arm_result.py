from pydantic import BaseModel

from .evaluation_summary import EvaluationSummary
from .ranking_delta import RankingDelta


class ArmResult(BaseModel):
    """One arm's full result: identity, population size, and its metrics (FR-3).

    `variant`/`model_column` are both `None` only for the fusion arm (AD-3) — every
    stored-vector arm has both set. `delta_vs_baseline` is `None` only for the baseline
    arm itself (nothing to diff against). `excluded_count` is the number of questions the
    corpus has that this arm could not support (FR-3: "excluded count is reported per arm
    rather than silently absorbed").
    """

    label: str
    variant: str | None
    model_column: str | None
    question_count: int
    excluded_count: int
    summary: EvaluationSummary
    delta_vs_baseline: RankingDelta | None
