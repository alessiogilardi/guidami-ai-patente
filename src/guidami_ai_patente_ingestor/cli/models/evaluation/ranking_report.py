from pydantic import BaseModel


class RankingAtK(BaseModel):
    """FR-4's ranking figures at one configured `k`.

    `hit_covered`/`hit_full` are the two denominators (keyword-covered subset vs. all
    measurable questions); `baseline_mean`/`baseline_spread_pp` are FR-3's random
    baseline, in percentage points; `lift_ratio`/`lift_points` report the same lift in
    both units, never mixed in one comparison.
    """

    hit_covered: float
    hit_full: float
    baseline_mean: float
    baseline_spread_pp: float
    lift_ratio: float
    lift_points: float


class RankingReport(BaseModel):
    """FR-3/FR-4's ranking report, keyed by `k` — never a single scalar.

    Deliberately carries no `metric_not_discriminating` (or similarly named) verdict
    field: with `N` repetitions of ~7000 draws the spread of the baseline mean cannot
    serve as a discrimination threshold (FR-3). `identity_note` and
    `image_comparability_note` must be non-empty: FR-4 requires both notes to be
    emitted alongside the numbers.
    """

    at_k: dict[int, RankingAtK]
    by_topic: dict[str, dict[int, RankingAtK]]
    by_image: dict[bool, dict[int, RankingAtK]]
    identity_note: str
    image_comparability_note: str
