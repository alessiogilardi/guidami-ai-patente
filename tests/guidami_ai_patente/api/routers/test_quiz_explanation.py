"""GET /quiz-questions/{number}/explanation, end to end (FR-5, FR-7, FR-11, FR-13)."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.agents.explanation_writer.dto import (
    ExplanationWriterRequest,
    ExplanationWriterResponse,
)
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.providers import LabelingStackProvider, LiveLabelingStackProvider
from guidami_ai_patente.services import ExplanationService
from labeling import EMBEDDING_MODEL_COLUMN
from labeling.agents.comma_labeler.dto import CommaLabelerRequest, CommaLabelerResponse

_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
    "quiz_answers",
    "quiz_questions",
    "article_commas",
    "articles",
)


@dataclass
class _WriterDouble:
    error: Exception | None = None
    requests: list[ExplanationWriterRequest] = field(default_factory=list)

    async def run(self, request: ExplanationWriterRequest) -> ExplanationWriterResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return ExplanationWriterResponse(
            explanation="La sosta è vietata perché la norma lo prevede.",
            cited_comma_numbers=[1],
        )


@dataclass
class _JudgeDouble:
    """Stands in for `CommaLabelerAgent` on a genuine cache miss (composed AD-29 test)."""

    ordinals: list[int]
    calls: int = 0

    async def run(self, request: CommaLabelerRequest) -> CommaLabelerResponse:
        self.calls += 1
        return CommaLabelerResponse(
            comma_numbers=self.ordinals, rationale="il comma giustifica la risposta"
        )


@pytest.fixture
def cached_question(api_client: TestClient) -> Iterator[PostgresClient]:
    """One question with a current labeling (matching the live epoch) and one comma."""
    container = get_default_container()
    client: PostgresClient = container.resolve(PostgresClientProvider).client
    epoch = container.resolve(LabelingStackProvider).epoch
    client.truncate(*_TABLES)

    article_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO articles (source, number, title, url, scraped_at) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            [
                "cds",
                "157",
                "Arresto, fermata e sosta dei veicoli",
                "https://example.test/art-157",
                datetime.now(UTC),
            ],
        )[0][0]
    )
    comma_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO article_commas (article_id, comma_number, position, text) "
                "VALUES (%s, %s, %s, %s) RETURNING id"
            ),
            [article_id, "3", 0, "È vietata la sosta negli spazi riservati."],
        )[0][0]
    )
    question_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO quiz_questions (number, question_id, topic, text, correct_answer) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            ["0001", 1, "sosta", "È vietata la sosta?", True],
        )[0][0]
    )
    run_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO labeling_runs (judge_model, prompt_version, candidate_variant, "
                "dense_k, text_k, lexeme_fields, shuffle_seed, corpus_commit, "
                "corpus_comma_count) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"
            ),
            [
                epoch.judge_model,
                epoch.prompt_version,
                epoch.candidate_variant,
                epoch.dense_k,
                epoch.text_k,
                list(epoch.lexeme_fields),
                42,
                "deadbeef",
                1,
            ],
        )[0][0]
    )
    labeling_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO quiz_labelings (run_id, quiz_question_id, rationale, "
                "has_supporting_commas) VALUES (%s, %s, %s, TRUE) RETURNING id"
            ),
            [run_id, question_id, "il comma giustifica la risposta"],
        )[0][0]
    )
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_comma_labels "
            "(labeling_id, article_comma_id, judge_rank, dense_rank) VALUES (%s, %s, 1, 1)"
        ),
        [labeling_id, comma_id],
    )
    yield client
    client.truncate(*_TABLES)


@pytest.fixture
def live_question(api_client: TestClient) -> Iterator[PostgresClient]:
    """One question with a query vector and no existing labeling — a genuine cache miss."""
    client: PostgresClient = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(*_TABLES)

    article_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO articles (source, number, title, url, scraped_at) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            [
                "cds",
                "157",
                "Arresto, fermata e sosta dei veicoli",
                "https://example.test/art-157",
                datetime.now(UTC),
            ],
        )[0][0]
    )
    client.execute(
        sql.SQL(
            "INSERT INTO article_commas (article_id, comma_number, position, text, embedding) "
            "VALUES (%s, %s, %s, %s, %s::vector)"
        ),
        [article_id, "3", 0, "È vietata la sosta negli spazi riservati.", [0.1] * 1536],
    )
    question_id = int(
        client.fetch(
            sql.SQL(
                "INSERT INTO quiz_questions (number, question_id, topic, text, correct_answer) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id"
            ),
            ["0001", 1, "sosta", "È vietata la sosta?", True],
        )[0][0]
    )
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_question_embeddings (quiz_question_id, variant, {column}) "
            "VALUES (%s, %s, %s::vector)"
        ).format(column=sql.Identifier(EMBEDDING_MODEL_COLUMN)),
        [question_id, "topic_text", [0.1] * 1536],
    )
    yield client
    client.truncate(*_TABLES)


def _install_writer(monkeypatch: pytest.MonkeyPatch, writer: _WriterDouble) -> None:
    """Substitutes the writer on the resolved service singleton.

    `register_instance` would refuse to displace the `@agent` registration, and the
    route resolves the same `ExplanationService` singleton this patches — monkeypatch
    restores the real agent for the next test.
    """
    service = get_default_container().resolve(ExplanationService)
    monkeypatch.setattr(service, "writer", writer)


def _install_judge(monkeypatch: pytest.MonkeyPatch, agent: _JudgeDouble) -> None:
    """Substitutes the live judge's agent, the same substitution mechanism as the writer.

    `LiveLabelingStackProvider` is built once (a container singleton), so resolving it
    here returns the exact `QuestionLabelingService` instance `CommaSelectorService`
    reads through its own `Autowired[LiveLabelingStackProvider]` field — patching its
    private `_agent` reaches the object a live request actually calls.
    """
    provider = get_default_container().resolve(LiveLabelingStackProvider)
    monkeypatch.setattr(provider.question_labeling, "_agent", agent)  # noqa: SLF001


@pytest.mark.integration
def test_a_cached_question_is_explained_with_its_citations(
    api_client: TestClient,
    cached_question: PostgresClient,
    monkeypatch: pytest.MonkeyPatch,
    registered_headers: dict[str, str],
) -> None:
    _install_writer(monkeypatch, _WriterDouble())

    response = api_client.get("/quiz-questions/0001/explanation", headers=registered_headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["status"] == "explained"
    assert body["explanation"]
    assert [citation["rank"] for citation in body["citations"]] == [1]
    assert body["citations"][0]["source"] == "cds"
    assert body["provenance"]["origin"] == "batch"


@pytest.mark.integration
def test_the_submitted_answer_reaches_the_writer(
    api_client: TestClient,
    cached_question: PostgresClient,
    monkeypatch: pytest.MonkeyPatch,
    registered_headers: dict[str, str],
) -> None:
    """FR-11: `?submitted=false` tells the writer the user got it wrong."""
    writer = _WriterDouble()
    _install_writer(monkeypatch, writer)

    api_client.get("/quiz-questions/0001/explanation?submitted=false", headers=registered_headers)

    assert writer.requests[0].submitted_answer is False


@pytest.mark.integration
def test_an_omitted_submitted_answer_is_still_served(
    api_client: TestClient,
    cached_question: PostgresClient,
    monkeypatch: pytest.MonkeyPatch,
    registered_headers: dict[str, str],
) -> None:
    writer = _WriterDouble()
    _install_writer(monkeypatch, writer)

    response = api_client.get("/quiz-questions/0001/explanation", headers=registered_headers)

    assert response.status_code == HTTPStatus.OK
    assert writer.requests[0].submitted_answer is None


@pytest.mark.integration
def test_a_question_with_no_vector_and_no_labeling_is_not_indexed(
    api_client: TestClient,
    cached_question: PostgresClient,
    monkeypatch: pytest.MonkeyPatch,
    registered_headers: dict[str, str],
) -> None:
    """FR-7: a pipeline gap, reported as a 200 with a machine-readable reason (AD-5)."""
    writer = _WriterDouble()
    _install_writer(monkeypatch, writer)
    cached_question.execute(sql.SQL("DELETE FROM quiz_labelings"))

    response = api_client.get("/quiz-questions/0001/explanation", headers=registered_headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["status"] == "insufficient_knowledge"
    assert body["reason"] == "not_indexed"
    assert (body["explanation"], body["citations"], body["judge_rationale"]) == (None, [], None)
    assert writer.requests == [], "FR-7: the writer is never called without commas"


@pytest.mark.integration
def test_an_unknown_number_is_a_404(
    api_client: TestClient, cached_question: PostgresClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.get("/quiz-questions/9999/explanation", headers=registered_headers)

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.integration
def test_a_writer_failure_is_a_503_and_keeps_the_labeling(
    api_client: TestClient,
    cached_question: PostgresClient,
    monkeypatch: pytest.MonkeyPatch,
    registered_headers: dict[str, str],
) -> None:
    """The plan's gate assertion 3 (AD-29, FR-13)."""
    _install_writer(monkeypatch, _WriterDouble(error=RuntimeError("provider is down")))

    response = api_client.get("/quiz-questions/0001/explanation", headers=registered_headers)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert "no_supporting_norm" not in response.text
    remaining = int(cached_question.fetch(sql.SQL("SELECT count(*) FROM quiz_labelings"))[0][0])
    assert remaining == 1, (
        "AD-29: the golden set records the judge's verdict, not the writer's success — "
        "so a writer outage must not roll the labeling back"
    )


@pytest.mark.integration
def test_the_check_still_reports_cached_after_a_writer_failure(
    api_client: TestClient,
    cached_question: PostgresClient,
    monkeypatch: pytest.MonkeyPatch,
    registered_headers: dict[str, str],
) -> None:
    """FR-13: the association exists even though the last render did not complete."""
    _install_writer(monkeypatch, _WriterDouble(error=RuntimeError("provider is down")))
    api_client.get("/quiz-questions/0001/explanation", headers=registered_headers)

    response = api_client.post(
        "/quiz-questions/0001/check",
        json={"answer": True, "session_id": "test-session"},
        headers=registered_headers,
    )

    assert response.json()["explanation_status"] == "cached"


@pytest.mark.integration
def test_a_writer_failure_after_a_live_judge_success_keeps_the_labeling_and_caches_the_retry(
    api_client: TestClient,
    live_question: PostgresClient,
    monkeypatch: pytest.MonkeyPatch,
    registered_headers: dict[str, str],
) -> None:
    """The plan's gate assertion 3, composed (AD-29, FR-13) — not two halves that never combine."""
    judge = _JudgeDouble([1])
    _install_judge(monkeypatch, judge)
    _install_writer(monkeypatch, _WriterDouble(error=RuntimeError("provider is down")))

    first = api_client.get("/quiz-questions/0001/explanation", headers=registered_headers)

    assert first.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    remaining = int(live_question.fetch(sql.SQL("SELECT count(*) FROM quiz_labelings"))[0][0])
    assert remaining == 1, "AD-29: the writer's failure must not roll back the judge's live write"

    _install_writer(monkeypatch, _WriterDouble())
    second = api_client.get("/quiz-questions/0001/explanation", headers=registered_headers)

    assert second.status_code == HTTPStatus.OK
    assert judge.calls == 1, "the retry must be a cache hit, not a second live judge run"
