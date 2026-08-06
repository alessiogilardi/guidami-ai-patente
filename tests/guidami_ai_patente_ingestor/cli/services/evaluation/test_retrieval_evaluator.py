import pytest

from domain.models.retrieval import QuizEvaluationRow
from guidami_ai_patente_ingestor.cli.services.evaluation.retrieval_evaluator import (
    RetrievalEvaluator,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig


class _FakeQuizReadRepository:
    """Local double for `QuizReadRepository`."""

    def __init__(self, rows: list[QuizEvaluationRow], variants: list[str]) -> None:
        self._rows = rows
        self._variants = variants

    def fetch_with_vectors(self, variant: str) -> list[QuizEvaluationRow]:
        return self._rows

    def available_variants(self) -> list[str]:
        return self._variants


class _FakeCorpusReadRepository:
    """Local double for `CorpusReadRepository`; unused when `evaluate` fails early."""


def test_raises_when_no_query_vectors() -> None:
    """T-10: an unpopulated or misconfigured `quiz_question_embeddings` table fails loudly.

    The error names both the configured variant and what the table actually contains,
    rather than reporting zeroes.
    """
    config = EvaluationConfig(quiz_embedding_variant="search_queries")
    quiz_repository = _FakeQuizReadRepository(rows=[], variants=["topic_text"])
    evaluator = RetrievalEvaluator(config, quiz_repository, _FakeCorpusReadRepository())

    with pytest.raises(ValueError) as exc_info:
        evaluator.evaluate()

    message = str(exc_info.value)
    assert "search_queries" in message
    assert "topic_text" in message


def test_step_names_match_executed_steps() -> None:
    """PD-5: the dry-run chain and the real run share one declared tuple of step names.

    No hand-maintained parallel list, so a step added to one is never silently missing
    from the other.
    """
    expected_steps = (
        "load quiz rows with vectors",
        "dense retrieval",
        "text retrieval",
        "coverage",
        "ranking + baseline",
        "adherence + signals",
        "keyword quality",
        "aggregate",
    )

    assert expected_steps == RetrievalEvaluator.STEP_NAMES
    assert len(RetrievalEvaluator.STEP_NAMES) == len(expected_steps)
