from unittest.mock import patch

from domain.models.retrieval import RetrievedComma
from guidami_ai_patente_ingestor.cli.models.evaluation import RankingAtK, RankingReport
from guidami_ai_patente_ingestor.cli.services.evaluation import (
    coverage_calculator,
    ranking_calculator,
)
from guidami_ai_patente_ingestor.cli.services.evaluation.ranking_calculator import (
    RankingCalculator,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig


def test_report_has_no_discrimination_verdict() -> None:
    report_fields = set(RankingReport.model_fields)
    at_k_fields = set(RankingAtK.model_fields)

    # FR-3: the spread-keyed flag was removed — a control that can never fire is
    # worse than none, because it reads as reassurance.
    assert not any("discriminating" in name for name in report_fields | at_k_fields)

    # FR-3: lift is reported both as a ratio and in percentage points, and it lives
    # per-k — lift@1 and lift@10 are different numbers, so a scalar on the report
    # would not say which k it describes.
    assert "lift_ratio" in at_k_fields
    assert "lift_points" in at_k_fields
    assert "at_k" in report_fields


def test_hit_uses_same_matching_as_coverage() -> None:
    calculator = RankingCalculator(EvaluationConfig())
    comma = RetrievedComma(
        source="cds",
        article_number="1",
        article_title="Titolo",
        comma_number="1",
        text="Testo con parola chiave.",
        distance=0.1,
    )

    with patch(
        "guidami_ai_patente_ingestor.cli.services.evaluation.ranking_calculator.matches_any_keyword",
        return_value=True,
    ) as mocked_matcher:
        calculator.is_hit(["parola"], [comma], k=1)

    mocked_matcher.assert_called()

    # FR-2's "identical fields" criterion: both calculators must import the exact same
    # function object, not two independent implementations of the same logic (the
    # divergence risk the plan names explicitly).
    assert coverage_calculator.matches_any_keyword is ranking_calculator.matches_any_keyword
