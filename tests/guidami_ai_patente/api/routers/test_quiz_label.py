"""POST /quiz-questions/{number}/label, end to end (FR-4, AD-2, AD-10)."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.providers import LiveLabelingStackProvider
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
class _JudgeDouble:
    ordinals: list[int]
    calls: int = 0

    async def run(self, request: CommaLabelerRequest) -> CommaLabelerResponse:
        self.calls += 1
        return CommaLabelerResponse(
            comma_numbers=self.ordinals, rationale="il comma giustifica la risposta"
        )


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


def _install_judge(monkeypatch: pytest.MonkeyPatch, agent: _JudgeDouble) -> None:
    """Substitutes the live judge's agent (same mechanism as `test_quiz_explanation.py`)."""
    provider = get_default_container().resolve(LiveLabelingStackProvider)
    monkeypatch.setattr(provider.question_labeling, "_agent", agent)  # noqa: SLF001


@pytest.mark.integration
def test_a_cache_miss_labels_live_and_returns_no_content(
    api_client: TestClient,
    live_question: PostgresClient,
    monkeypatch: pytest.MonkeyPatch,
    registered_headers: dict[str, str],
) -> None:
    judge = _JudgeDouble([1])
    _install_judge(monkeypatch, judge)

    response = api_client.post("/quiz-questions/0001/label", headers=registered_headers)

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert judge.calls == 1
    labelings = live_question.fetch(sql.SQL("SELECT count(*) FROM quiz_labelings"))[0][0]
    assert int(labelings) == 1


@pytest.mark.integration
def test_a_second_call_is_a_cache_hit_and_calls_no_judge(
    api_client: TestClient,
    live_question: PostgresClient,
    monkeypatch: pytest.MonkeyPatch,
    registered_headers: dict[str, str],
) -> None:
    """FR-4: idempotent — the second call issues no retrieval and no judge call."""
    _install_judge(monkeypatch, _JudgeDouble([1]))
    api_client.post("/quiz-questions/0001/label", headers=registered_headers)

    second_judge = _JudgeDouble([1])
    _install_judge(monkeypatch, second_judge)
    response = api_client.post("/quiz-questions/0001/label", headers=registered_headers)

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert second_judge.calls == 0, "the retry must be a cache hit, not a second live judge run"


@pytest.mark.integration
def test_labeling_makes_the_check_response_report_cached(
    api_client: TestClient,
    live_question: PostgresClient,
    monkeypatch: pytest.MonkeyPatch,
    registered_headers: dict[str, str],
) -> None:
    _install_judge(monkeypatch, _JudgeDouble([1]))
    api_client.post("/quiz-questions/0001/label", headers=registered_headers)

    response = api_client.post(
        "/quiz-questions/0001/check",
        json={"answer": True, "session_id": "test-session"},
        headers=registered_headers,
    )

    assert response.json()["explanation_status"] == "cached"


@pytest.mark.integration
def test_an_unknown_number_is_a_404(
    api_client: TestClient,
    live_question: PostgresClient,
    registered_headers: dict[str, str],
) -> None:
    """Consistency with /check and /explanation (LabelingService's own 404 check)."""
    response = api_client.post("/quiz-questions/9999/label", headers=registered_headers)

    assert response.status_code == HTTPStatus.NOT_FOUND
