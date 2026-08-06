import math

from guidami_ai_patente_ingestor.cli.models.evaluation.keyword_quality_report import (
    KeywordQualityReport,
)
from guidami_ai_patente_ingestor.cli.services.evaluation.keyword_quality_calculator import (
    KeywordQualityCalculator,
)


class _FakeCorpusReadRepository:
    """Local double: unused by `hit_adherence_association`, a pure-stats computation."""


def test_association_is_nan_on_zero_variance() -> None:
    calculator = KeywordQualityCalculator(_FakeCorpusReadRepository())
    hits = [True, True, True]
    adherences = [0.1, 0.2, 0.3]

    result = calculator.hit_adherence_association(hits, adherences)

    assert math.isnan(result)
    assert result != 0.0


def test_report_states_not_an_independence_test() -> None:
    report = KeywordQualityReport(
        zero_match_share=0.1,
        document_frequency_distribution={"stop": 5},
        hit_adherence_association=0.3,
    )

    note_fields = [
        name for name, field in type(report).model_fields.items() if field.annotation is str
    ]

    assert note_fields, "expected a constant string note field on KeywordQualityReport"
    notes = [getattr(report, name) for name in note_fields]
    assert any(note.strip() for note in notes)
    assert any("question text" in note.lower() or "keyword" in note.lower() for note in notes)
