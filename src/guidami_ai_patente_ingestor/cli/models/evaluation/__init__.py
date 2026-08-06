"""CLI-only DTOs for `ingest evaluate retrieval` (spec 0007, `.claude/rules/cli-structure.md`)."""

from .coverage_report import CoverageReport
from .evaluation_summary import EvaluationSummary
from .keyword_quality_report import KeywordQualityReport
from .question_outcome import QuestionOutcome
from .ranking_report import RankingAtK, RankingReport
from .signal_report import SignalReport

__all__ = [
    "CoverageReport",
    "EvaluationSummary",
    "KeywordQualityReport",
    "QuestionOutcome",
    "RankingAtK",
    "RankingReport",
    "SignalReport",
]
