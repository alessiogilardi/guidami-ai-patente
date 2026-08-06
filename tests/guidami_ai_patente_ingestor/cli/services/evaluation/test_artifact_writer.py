from pathlib import Path

from domain.models.retrieval import QuizEvaluationRow, RetrievedComma
from guidami_ai_patente_ingestor.cli.models.evaluation.coverage_report import CoverageReport
from guidami_ai_patente_ingestor.cli.models.evaluation.evaluation_summary import (
    EvaluationSummary,
)
from guidami_ai_patente_ingestor.cli.models.evaluation.keyword_quality_report import (
    KeywordQualityReport,
)
from guidami_ai_patente_ingestor.cli.models.evaluation.question_outcome import QuestionOutcome
from guidami_ai_patente_ingestor.cli.models.evaluation.ranking_report import (
    RankingAtK,
    RankingReport,
)
from guidami_ai_patente_ingestor.cli.models.evaluation.signal_report import SignalReport
from guidami_ai_patente_ingestor.cli.services.evaluation.artifact_writer import (
    EvaluationArtifactWriter,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig


def _build_summary() -> EvaluationSummary:
    """Builds a minimal, self-consistent `EvaluationSummary`.

    Field names for the nested reports mirror the plan's T-6/T-7/T-9 shapes exactly
    (`RankingReport` keyed by `k` via `RankingAtK`; `parameters` embeds `EvaluationConfig`
    verbatim rather than duplicating its field names). If the real schema differs, only
    this helper needs updating — the assertions below check serialized content, not
    field names.
    """
    coverage = CoverageReport.model_construct(
        text_score_median=0.05,
        text_score_quartiles=(0.02, 0.08),
        text_share_above={0.01: 0.9, 0.02: 0.7, 0.05: 0.3, 0.10: 0.1},
        keyword_matches_nothing=12,
        keyword_band={1: 100, 2: 50, 3: 30, 5: 20, 10: 10, 20: 5, 50: 2, 100: 1, 250: 0, 500: 0},
        not_measurable=3,
        by_topic={},
    )
    ranking = RankingReport.model_construct(
        at_k={
            1: RankingAtK(
                hit_covered=0.8,
                hit_full=0.6,
                baseline_mean=0.1,
                baseline_spread_pp=1.5,
                lift_ratio=4.0,
                lift_points=45.0,
            )
        },
        by_topic={},
        by_image={},
        identity_note="full ~= covered * coverage_rate (arithmetic identity, not a cost)",
        image_comparability_note="image/non-image populations are not comparable on this metric",
    )
    signals = SignalReport.model_construct(
        adherence_median=0.4,
        adherence_quartiles=(0.2, 0.6),
        adherence_by_field={"weighted": 0.4, "title": 0.3, "text": 0.35},
        overlap_median=0.5,
        overlap_quartiles=(0.3, 0.7),
        margin_median=0.1,
        margin_quartiles=(0.05, 0.15),
        zero_overlap_share=0.05,
    )
    keyword_quality = KeywordQualityReport.model_construct(
        zero_match_share=0.1,
        document_frequency_distribution={"stop": 5},
        hit_adherence_association=0.3,
    )
    return EvaluationSummary.model_construct(
        schema_version=1,
        parameters=EvaluationConfig(),
        coverage=coverage,
        ranking=ranking,
        signals=signals,
        keyword_quality=keyword_quality,
    )


def test_summary_is_byte_identical_across_runs(tmp_path: Path) -> None:
    """T-9: two writes of the same summary content must diff empty (sorted-key JSON)."""
    summary = _build_summary()
    first_writer = EvaluationArtifactWriter(tmp_path / "run-a", tmp_path / "run-a")
    second_writer = EvaluationArtifactWriter(tmp_path / "run-b", tmp_path / "run-b")

    first_path = first_writer.write_summary(summary)
    second_path = second_writer.write_summary(summary)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_judge_export_records_are_self_contained(tmp_path: Path) -> None:
    """T-9: each judge-export record is self-contained.

    Question text, correct answer, and the retrieved commas' source are all present in
    the exported artifact.
    """
    row = QuizEvaluationRow(
        id=1,
        number="0001",
        topic="segnaletica",
        text="Quale segnale indica un divieto di sosta?",
        correct_answer=True,
        exact_keywords=None,
        image_filename=None,
        embedding=[0.1, 0.2],
    )
    comma = RetrievedComma(
        source="cds",
        article_number="7",
        article_title="Segnaletica stradale",
        comma_number="1",
        text="Testo del comma.",
        distance=0.2,
    )
    outcome = QuestionOutcome.model_construct(row=row, dense_top_k=[comma], fts_top_k=[comma])
    writer = EvaluationArtifactWriter(tmp_path / "committed", tmp_path / "run")

    export_path = writer.write_judge_export([outcome])

    content = export_path.read_text(encoding="utf-8")
    assert row.text in content
    assert "true" in content.lower() or "True" in content
    assert comma.source in content
