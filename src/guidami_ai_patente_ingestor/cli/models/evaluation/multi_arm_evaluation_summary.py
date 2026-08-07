from pydantic import BaseModel

from .arm_result import ArmResult


class MultiArmEvaluationSummary(BaseModel):
    """FR-3's top-level report: every arm, keyed by label, in a stable declared order.

    `arms` uses a plain `dict[str, ArmResult]` (not a list) so a diff between two runs
    with the same arm set stays keyed by label rather than by position (FR-7's diffable-
    output requirement, inherited from spec 0007, still applies).
    """

    schema_version: int = 1
    baseline_label: str
    arms: dict[str, ArmResult]
