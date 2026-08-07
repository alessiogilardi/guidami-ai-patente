from guidami_ai_patente_ingestor.cli.models.evaluation import (
    ArmResult,
    CoverageReport,
    EvaluationSummary,
    KeywordQualityReport,
    RankingReport,
    SignalReport,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig


def _evaluation_summary() -> EvaluationSummary:
    return EvaluationSummary(
        parameters=EvaluationConfig(),
        coverage=CoverageReport(
            text_score_median=0.0,
            text_score_quartiles=(0.0, 0.0),
            text_share_above={},
            keyword_matches_nothing=0,
            keyword_band={},
            not_measurable=0,
            by_topic={},
        ),
        ranking=RankingReport(
            at_k={},
            by_topic={},
            by_image={},
            identity_note="note",
            image_comparability_note="note",
        ),
        signals=SignalReport(
            adherence_median=0.0,
            adherence_quartiles=(0.0, 0.0),
            adherence_by_field={},
            overlap_median=0.0,
            overlap_quartiles=(0.0, 0.0),
            margin_median=0.0,
            margin_quartiles=(0.0, 0.0),
            zero_overlap_share=0.0,
        ),
        keyword_quality=KeywordQualityReport(
            zero_match_share=0.0,
            document_frequency_distribution={},
            hit_adherence_association=0.0,
        ),
    )


def test_construct_baseline_arm_with_no_delta() -> None:
    result = ArmResult(
        label="search_queries",
        variant="search_queries",
        model_column="embedding_3_small",
        question_count=10,
        excluded_count=0,
        summary=_evaluation_summary(),
        delta_vs_baseline=None,
    )

    assert result.label == "search_queries"
    assert result.delta_vs_baseline is None


def test_construct_fusion_arm_has_no_variant_or_model_column() -> None:
    result = ArmResult(
        label="fusion",
        variant=None,
        model_column=None,
        question_count=8,
        excluded_count=2,
        summary=_evaluation_summary(),
        delta_vs_baseline=None,
    )

    assert result.variant is None
    assert result.model_column is None
