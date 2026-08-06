from pydantic import BaseModel

from guidami_ai_patente_ingestor.configs import EvaluationConfig

from .coverage_report import CoverageReport
from .keyword_quality_report import KeywordQualityReport
from .ranking_report import RankingReport
from .signal_report import SignalReport


class EvaluationSummary(BaseModel):
    """FR-7's committed, versioned metrics summary — one shape, diffable across runs.

    `parameters` embeds the `EvaluationConfig` actually used (config + any CLI
    override) verbatim, satisfying FR-7's "run parameters actually used" without
    duplicating field names that would then drift from `EvaluationConfig` (T-1).
    Deliberately carries no timestamp: FR-7 requires two runs of the same corpus,
    seed and parameters to diff empty, and a timestamp would make every run differ.
    Run time already lives in `manifest.json`.
    """

    schema_version: int = 1
    parameters: EvaluationConfig
    coverage: CoverageReport
    ranking: RankingReport
    signals: SignalReport
    keyword_quality: KeywordQualityReport
