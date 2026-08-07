"""CLI-only DTOs for `ingest evaluate retrieval` (spec 0007, `.claude/rules/cli-structure.md`)."""

from .arm_result import ArmResult
from .coverage_report import CoverageReport
from .evaluation_summary import EvaluationSummary
from .keyword_quality_report import KeywordQualityReport
from .multi_arm_evaluation_summary import MultiArmEvaluationSummary
from .question_outcome import QuestionOutcome
from .ranking_delta import RankingDelta
from .ranking_report import RankingAtK, RankingReport
from .signal_report import SignalReport

__all__ = [
    "ArmResult",
    "CoverageReport",
    "EvaluationSummary",
    "KeywordQualityReport",
    "MultiArmEvaluationSummary",
    "QuestionOutcome",
    "RankingAtK",
    "RankingDelta",
    "RankingReport",
    "SignalReport",
]
