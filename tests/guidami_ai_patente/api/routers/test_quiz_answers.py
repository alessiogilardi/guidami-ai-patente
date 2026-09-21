"""End-to-end tests for GET /quiz-answers/summary (spec 0016, FR-9, AD-16)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider

_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "quiz_question_embeddings",
    "quiz_answers",
    "users",
    "quiz_questions",
)
_QUESTION = ("0001", 1, "segnaletica", "Il segnale vieta il sorpasso?", True, None)


@pytest.fixture
def bank(api_client: TestClient) -> Iterator[PostgresClient]:
    client = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(*_TABLES)
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_questions "
            "(number, question_id, topic, text, correct_answer, image_filename) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        ),
        list(_QUESTION),
    )
    yield client
    client.truncate(*_TABLES)


@pytest.mark.integration
def test_the_summary_counts_answered_and_correct(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    api_client.post(
        "/quiz-questions/0001/check",
        json={"answer": True, "session_id": "seed-xyz"},
        headers=registered_headers,
    )
    api_client.post(
        "/quiz-questions/0001/check",
        json={"answer": False, "session_id": "seed-xyz"},
        headers=registered_headers,
    )

    response = api_client.get(
        "/quiz-answers/summary", params={"session_id": "seed-xyz"}, headers=registered_headers
    )

    assert response.status_code == 200
    assert response.json() == {
        "answered": 2,
        "correct": 1,
        "by_topic": [{"topic": "segnaletica", "answered": 2, "correct": 1}],
        "wrong_questions": [{"number": "0001", "text": "Il segnale vieta il sorpasso?"}],
    }


@pytest.mark.integration
def test_an_unplayed_session_summarizes_to_zero(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.get(
        "/quiz-answers/summary", params={"session_id": "never-played"}, headers=registered_headers
    )

    assert response.json() == {
        "answered": 0,
        "correct": 0,
        "by_topic": [],
        "wrong_questions": [],
    }


@pytest.mark.integration
def test_the_summary_endpoint_is_gated(bank: PostgresClient, api_client: TestClient) -> None:
    response = api_client.get(
        "/quiz-answers/summary",
        params={"session_id": "x"},
        headers={"X-Telegram-User-Id": "999"},
    )

    assert response.status_code == 403
