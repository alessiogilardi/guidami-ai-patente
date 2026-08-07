from pydantic import BaseModel


class RankingDelta(BaseModel):
    """FR-3's per-arm delta against the baseline arm.

    `hit_full` at each configured `k`, in percentage points (PD-12) — the same figure and
    unit `RankingCalculator` already reports for the random-baseline lift, so no new
    metric definition is introduced. Positive means the arm beats the baseline at that `k`.
    """

    hit_full_delta_points: dict[int, float]
