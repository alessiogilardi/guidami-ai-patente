from pydantic import BaseModel


class SignalReport(BaseModel):
    """FR-5/FR-6's judge-free signals: lexical adherence, dense/FTS agreement, margin.

    `adherence_by_field` reports the weighted, title-only and text-only `ts_rank`
    medians separately, so each field's contribution is visible rather than assumed
    (FR-5). `overlap_median`/`zero_overlap_share` and `margin_median` are FR-6's
    dense/FTS agreement and distance-margin signals, at one fixed depth
    (`max(k_values)`).
    """

    adherence_median: float
    adherence_quartiles: tuple[float, float]
    adherence_by_field: dict[str, float]
    overlap_median: float
    overlap_quartiles: tuple[float, float]
    margin_median: float
    margin_quartiles: tuple[float, float]
    zero_overlap_share: float
