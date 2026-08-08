from domain.models.retrieval import QuizEvaluationRow, RetrievedComma
from guidami_ai_patente_ingestor.cli.services.evaluation.retrieval_evaluator import (
    RetrievalEvaluator,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig


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


def _row(number: str = "0001") -> QuizEvaluationRow:
    return QuizEvaluationRow(
        id=1,
        number=number,
        topic="segnaletica",
        text="Domanda di prova?",
        correct_answer=True,
        exact_keywords=["keyword"],
        image_filename=None,
        image_description=None,
        embedding=[0.1, 0.2],
    )


def test_evaluate_takes_preloaded_rows() -> None:
    """T-14: RetrievalEvaluator no longer owns row loading — the caller supplies rows."""
    config = EvaluationConfig(quiz_embedding_variant="search_queries")
    evaluator = RetrievalEvaluator(config, _FakeCorpusReadRepository())

    summary, outcomes = evaluator.evaluate([_row()])

    assert len(outcomes) == 1
    assert outcomes[0].row.number == "0001"
    assert summary.parameters == config


def test_evaluate_with_no_rows_produces_empty_outcomes() -> None:
    """Empty input is no longer fatal (T-14): the caller decides what an empty arm means."""
    config = EvaluationConfig(quiz_embedding_variant="search_queries")
    evaluator = RetrievalEvaluator(config, _FakeCorpusReadRepository())

    _summary, outcomes = evaluator.evaluate([])

    assert outcomes == []


def test_step_names_match_executed_steps() -> None:
    """PD-5: the dry-run chain and the real run share one declared tuple of step names.

    No hand-maintained parallel list, so a step added to one is never silently missing
    from the other. Row loading is no longer one of RetrievalEvaluator's own steps (T-14).
    """
    expected_steps = (
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
