"""CLI-only evaluation services for `ingest evaluate retrieval` (spec 0007).

Deciding test per `.claude/rules/cli-structure.md`: these have exactly one
consumer, the `evaluate` command — unlike the read repositories in
`commons/repositories/db/`, which the future FastAPI app will also need.
"""

from .adherence_calculator import AdherenceCalculator
from .artifact_writer import EvaluationArtifactWriter
from .coverage_calculator import CoverageCalculator
from .keyword_quality_calculator import KeywordQualityCalculator
from .multi_arm_retrieval_evaluator import MultiArmRetrievalEvaluator
from .ranking_calculator import RankingCalculator
from .retrieval_evaluator import RetrievalEvaluator

__all__ = [
    "AdherenceCalculator",
    "CoverageCalculator",
    "EvaluationArtifactWriter",
    "KeywordQualityCalculator",
    "MultiArmRetrievalEvaluator",
    "RankingCalculator",
    "RetrievalEvaluator",
]
