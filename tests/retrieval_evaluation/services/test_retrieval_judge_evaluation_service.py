"""Tests for RetrievalJudgeEvaluationService."""

import random
from unittest.mock import MagicMock

from commons.repositories.db import CorpusReadRepository, QuizReadRepository
from domain.models.retrieval import QuizEvaluationRow, RetrievedComma
from retrieval_evaluation.agents import RetrievalJudgeAgent
from retrieval_evaluation.agents.dto.retrieval_judge import RetrievalJudgeResponse
from retrieval_evaluation.services import RetrievalJudgeEvaluationService


def _make_row(number: str) -> QuizEvaluationRow:
    return QuizEvaluationRow(
        id=1,
        number=number,
        topic="Segnaletica",
        text="Il segnale indica obbligo di fermata.",
        correct_answer=True,
        exact_keywords=["stop"],
        image_filename=None,
        embedding=[0.1, 0.2],
    )


def _make_comma() -> RetrievedComma:
    return RetrievedComma(
        source="cds",
        article_number="41",
        article_title="Segnali di pericolo",
        comma_number="1",
        text="Il segnale di stop impone l'obbligo di arresto.",
        distance=0.05,
    )


def _make_service(
    quiz_repository: QuizReadRepository, corpus_repository: CorpusReadRepository, agent: object
) -> RetrievalJudgeEvaluationService:
    return RetrievalJudgeEvaluationService(
        k=10,
        variant="search_queries",
        quiz_repository=quiz_repository,
        corpus_repository=corpus_repository,
        agent=agent,  # type: ignore[arg-type]
    )


def test_evaluate_judges_a_random_sample_of_n_questions() -> None:
    rows = [_make_row(str(i)) for i in range(5)]
    quiz_repository = MagicMock(spec=QuizReadRepository)
    quiz_repository.fetch_with_vectors.return_value = rows
    corpus_repository = MagicMock(spec=CorpusReadRepository)
    corpus_repository.dense_top_k.return_value = [_make_comma()]
    agent = MagicMock(spec=RetrievalJudgeAgent)
    agent.run_sync.return_value = RetrievalJudgeResponse(is_clear=True, rationale="Chiaro.")

    service = _make_service(quiz_repository, corpus_repository, agent)
    results = service.evaluate(n=3, rng=random.Random(0))

    assert len(results) == 3
    assert all(result.is_clear for result in results)
    quiz_repository.fetch_with_vectors.assert_called_once_with("search_queries")


def test_evaluate_retrieves_top_k_commas_per_question() -> None:
    rows = [_make_row("1")]
    quiz_repository = MagicMock(spec=QuizReadRepository)
    quiz_repository.fetch_with_vectors.return_value = rows
    corpus_repository = MagicMock(spec=CorpusReadRepository)
    corpus_repository.dense_top_k.return_value = [_make_comma()]
    agent = MagicMock(spec=RetrievalJudgeAgent)
    agent.run_sync.return_value = RetrievalJudgeResponse(is_clear=False, rationale="Non chiaro.")

    service = _make_service(quiz_repository, corpus_repository, agent)
    service.evaluate(n=1, rng=random.Random(0))

    corpus_repository.dense_top_k.assert_called_once_with(rows[0].embedding, 10)


def test_evaluate_caps_n_at_the_number_of_available_rows() -> None:
    rows = [_make_row("1")]
    quiz_repository = MagicMock(spec=QuizReadRepository)
    quiz_repository.fetch_with_vectors.return_value = rows
    corpus_repository = MagicMock(spec=CorpusReadRepository)
    corpus_repository.dense_top_k.return_value = [_make_comma()]
    agent = MagicMock(spec=RetrievalJudgeAgent)
    agent.run_sync.return_value = RetrievalJudgeResponse(is_clear=False, rationale="Non chiaro.")

    service = _make_service(quiz_repository, corpus_repository, agent)
    results = service.evaluate(n=5, rng=random.Random(0))

    assert len(results) == 1
    assert results[0].quiz_number == "1"
    assert results[0].is_clear is False
    assert results[0].rationale == "Non chiaro."


def test_evaluate_all_judges_every_available_row() -> None:
    rows = [_make_row(str(i)) for i in range(5)]
    quiz_repository = MagicMock(spec=QuizReadRepository)
    quiz_repository.fetch_with_vectors.return_value = rows
    corpus_repository = MagicMock(spec=CorpusReadRepository)
    corpus_repository.dense_top_k.return_value = [_make_comma()]
    agent = MagicMock(spec=RetrievalJudgeAgent)
    agent.run_sync.return_value = RetrievalJudgeResponse(is_clear=True, rationale="Chiaro.")

    service = _make_service(quiz_repository, corpus_repository, agent)
    results = service.evaluate_all()

    assert [result.quiz_number for result in results] == [row.number for row in rows]
    assert all(result.is_clear for result in results)
    quiz_repository.fetch_with_vectors.assert_called_once_with("search_queries")
