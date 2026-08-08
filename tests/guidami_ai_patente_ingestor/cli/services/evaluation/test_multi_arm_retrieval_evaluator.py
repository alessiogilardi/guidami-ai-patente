"""Tests for MultiArmRetrievalEvaluator (FR-3: every metric per (variant, model) arm).

NOTE on the first test below (name omitted here, too long for this line's limit):
the plan's own literal `available_variants()` fixture (`["combined", "search_queries",
"text"]`, no `"topic_text"`) contradicts PD-1/T-16's own `_load_fusion_rows` description,
which requires *both* `"topic_text"` and `"text"` to be loaded before a fusion arm can be
computed (confirmed by this file's own
`test_fusion_arm_absent_when_topic_text_or_text_variant_missing_entirely`, which asserts
the opposite outcome from the same missing-`"topic_text"` precondition). This test adds
`"topic_text"` to the fixture's available variants so the fusion arm is actually
computable, and asserts `"topic_text"` as its own arm too — flagged here, and in the
red-phase handoff, for the plan/spec to be reconciled rather than silently guessed at.
"""

import pytest

from domain.models.retrieval import QuizEvaluationRow, RetrievedComma
from guidami_ai_patente_ingestor.cli.services.evaluation.multi_arm_retrieval_evaluator import (
    MultiArmRetrievalEvaluator,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig


def _row(number: str = "0001") -> QuizEvaluationRow:
    return QuizEvaluationRow(
        id=int(number),
        number=number,
        topic="segnaletica",
        text="Domanda di prova?",
        correct_answer=True,
        exact_keywords=["keyword"],
        image_filename=None,
        image_description=None,
        embedding=[0.1, 0.2],
    )


def _comma(article_number: str = "1") -> RetrievedComma:
    return RetrievedComma(
        source="cds",
        article_number=article_number,
        article_title="Titolo",
        comma_number="1",
        text="Testo del comma.",
        distance=0.1,
    )


class _FakeCorpusReadRepository:
    """Local double for `CorpusReadRepository`, stubbed with fixed, deterministic results."""

    def dense_top_k(self, embedding: list[float], k: int) -> list[RetrievedComma]:
        return [_comma()]

    def text_top_k(self, lexemes: list[str], k: int) -> list[RetrievedComma]:
        return [_comma()]

    def random_top_k(self, k: int, seed_key: str) -> list[RetrievedComma]:
        return [_comma()]

    def best_text_rank(self, lexemes: list[str]) -> float:
        return 0.5

    def keyword_document_frequency(self, keyword: str) -> int:
        return 3

    def rank_text(
        self, lexemes: list[str], article_title: str, text: str
    ) -> tuple[float, float, float]:
        return 0.5, 0.4, 0.3


class _FakeQuizReadRepository:
    """Local double for `QuizReadRepository`."""

    def __init__(
        self,
        variants: list[str],
        model_columns: list[str],
        rows_by_variant: dict[str, list[QuizEvaluationRow]],
    ) -> None:
        self._variants = variants
        self._model_columns = model_columns
        self._rows_by_variant = rows_by_variant

    def available_variants(self) -> list[str]:
        return self._variants

    def populated_model_columns(self) -> list[str]:
        return self._model_columns

    def fetch_with_vectors(self, variant: str, model_column: str) -> list[QuizEvaluationRow]:
        return self._rows_by_variant.get(variant, [])


def test_evaluate_returns_one_arm_per_populated_variant_labelled_by_variant_when_one_model_column() -> (  # noqa: E501
    None
):
    rows_by_variant = {
        "combined": [_row("0001"), _row("0002")],
        "search_queries": [_row("0001"), _row("0002")],
        "text": [_row("0001"), _row("0002")],
        "topic_text": [_row("0001"), _row("0002")],
    }
    quiz_repository = _FakeQuizReadRepository(
        variants=["combined", "search_queries", "text", "topic_text"],
        model_columns=["embedding_3_small"],
        rows_by_variant=rows_by_variant,
    )
    config = EvaluationConfig(quiz_embedding_variant="search_queries")
    evaluator = MultiArmRetrievalEvaluator(
        config,
        quiz_repository,  # type: ignore[arg-type]
        _FakeCorpusReadRepository(),  # type: ignore[arg-type]
    )

    summary, _outcomes = evaluator.evaluate()

    assert set(summary.arms) == {"combined", "search_queries", "text", "topic_text", "fusion"}
    assert summary.baseline_label == "search_queries"
    assert summary.arms["search_queries"].delta_vs_baseline is None
    assert summary.arms["combined"].delta_vs_baseline is not None


def test_arm_label_includes_model_column_when_more_than_one_populated() -> None:
    rows_by_variant = {"search_queries": [_row("0001")]}
    quiz_repository = _FakeQuizReadRepository(
        variants=["search_queries"],
        model_columns=["embedding_3_small", "embedding_3_large"],
        rows_by_variant=rows_by_variant,
    )
    config = EvaluationConfig(quiz_embedding_variant="search_queries")
    evaluator = MultiArmRetrievalEvaluator(
        config,
        quiz_repository,  # type: ignore[arg-type]
        _FakeCorpusReadRepository(),  # type: ignore[arg-type]
    )

    summary, _outcomes = evaluator.evaluate()

    assert "search_queries::embedding_3_small" in summary.arms
    assert "search_queries::embedding_3_large" in summary.arms


def test_excluded_count_is_total_minus_arm_population() -> None:
    rows_by_variant = {
        "search_queries": [_row("0001"), _row("0002")],
        "text": [_row("0001")],
    }
    quiz_repository = _FakeQuizReadRepository(
        variants=["search_queries", "text"],
        model_columns=["embedding_3_small"],
        rows_by_variant=rows_by_variant,
    )
    config = EvaluationConfig(quiz_embedding_variant="search_queries")
    evaluator = MultiArmRetrievalEvaluator(
        config,
        quiz_repository,  # type: ignore[arg-type]
        _FakeCorpusReadRepository(),  # type: ignore[arg-type]
    )

    summary, _outcomes = evaluator.evaluate()

    assert summary.arms["search_queries"].excluded_count == 0
    assert summary.arms["text"].excluded_count == 1


def test_missing_baseline_variant_raises_value_error_naming_available_variants() -> None:
    rows_by_variant = {"text": [_row("0001")]}
    quiz_repository = _FakeQuizReadRepository(
        variants=["text"], model_columns=["embedding_3_small"], rows_by_variant=rows_by_variant
    )
    config = EvaluationConfig(quiz_embedding_variant="search_queries")
    evaluator = MultiArmRetrievalEvaluator(
        config,
        quiz_repository,  # type: ignore[arg-type]
        _FakeCorpusReadRepository(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError) as exc_info:
        evaluator.evaluate()

    message = str(exc_info.value)
    assert "search_queries" in message
    assert "text" in message


def test_fusion_arm_absent_when_topic_text_or_text_variant_missing_entirely() -> None:
    """PD-1: the fusion arm needs both `topic_text` and `text` rows; missing either → no arm."""
    rows_by_variant = {"search_queries": [_row("0001")]}
    quiz_repository = _FakeQuizReadRepository(
        variants=["search_queries"],
        model_columns=["embedding_3_small"],
        rows_by_variant=rows_by_variant,
    )
    config = EvaluationConfig(quiz_embedding_variant="search_queries")
    evaluator = MultiArmRetrievalEvaluator(
        config,
        quiz_repository,  # type: ignore[arg-type]
        _FakeCorpusReadRepository(),  # type: ignore[arg-type]
    )

    summary, _outcomes = evaluator.evaluate()

    assert "fusion" not in summary.arms
