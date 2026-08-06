from pydantic import BaseModel


class CoverageReport(BaseModel):
    """FR-2's corpus coverage report: two distributions, never a single percentage.

    `text_share_above` maps each configured `ts_rank` threshold to the share of
    questions above it. `keyword_band` maps each configured document-frequency cutoff
    to the count of questions whose most selective matching keyword exceeds it — a
    higher document frequency means a less selective keyword. `keyword_matches_nothing`
    is a lower bound on the uncovered population, not a count (FR-2). `not_measurable`
    counts questions with no `exact_keywords` at all. `by_topic` breaks every figure down
    per topic, worst-first.
    """

    text_score_median: float
    text_score_quartiles: tuple[float, float]
    text_share_above: dict[float, float]
    keyword_matches_nothing: int
    keyword_band: dict[int, int]
    not_measurable: int
    by_topic: dict[str, "CoverageReport"]
