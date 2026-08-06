from domain.models.retrieval import QuizEvaluationRow
from guidami_ai_patente_ingestor.cli.services.evaluation.coverage_calculator import (
    CoverageCalculator,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig


class _FakeCorpusReadRepository:
    """Local double: only the method `CoverageCalculator.text_score` calls."""

    def __init__(self, best_text_rank: float) -> None:
        self._best_text_rank = best_text_rank
        self.received_lexemes: list[str] | None = None

    def best_text_rank(self, lexemes: list[str]) -> float:
        self.received_lexemes = lexemes
        return self._best_text_rank


def _build_row(number: str, topic: str) -> QuizEvaluationRow:
    return QuizEvaluationRow(
        id=1,
        number=number,
        topic=topic,
        text="Domanda di prova?",
        correct_answer=True,
        exact_keywords=None,
        image_filename=None,
        embedding=[0.1, 0.2],
    )


def test_text_score_is_continuous_not_boolean() -> None:
    repository = _FakeCorpusReadRepository(best_text_rank=0.0634)
    calculator = CoverageCalculator(EvaluationConfig(), repository)  # pyright: ignore[reportArgumentType]

    result = calculator.text_score("qualunque testo")

    assert result == 0.0634
    assert isinstance(result, float)
    assert result is not True


def test_build_report_reports_band_not_single_percentage() -> None:
    config = EvaluationConfig()
    repository = _FakeCorpusReadRepository(best_text_rank=0.05)
    calculator = CoverageCalculator(config, repository)  # pyright: ignore[reportArgumentType]
    rows = [_build_row("0001", "segnaletica"), _build_row("0002", "segnaletica")]
    scores = [0.03, 0.07]
    best_dfs = [None, 5]

    report = calculator.build_report(rows, scores, best_dfs)

    percentage_fields = [
        name
        for name in type(report).model_fields
        if "percentage" in name.lower() or name == "coverage"
    ]
    assert percentage_fields == []
    assert len(report.keyword_band) == len(config.keyword_df_cutoffs)
