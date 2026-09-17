"""End-to-end tests for the no-LLM quiz endpoints (FR-1, FR-2, FR-3, FR-4, FR-16)."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.providers import LabelingStackProvider
from labeling.models import LabelingEpoch

_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
    "quiz_answers",
    "quiz_questions",
)

_QUESTIONS = (
    ("0001", 1, "segnaletica", "Il segnale vieta il sorpasso?", True, "s0001.jpeg"),
    ("0002", 2, "segnaletica", "Il segnale indica un pericolo?", False, None),
    ("0003", 3, "velocità", "Il limite in autostrada è 130 km/h?", True, None),
)


@pytest.fixture
def bank(api_client: TestClient) -> Iterator[PostgresClient]:
    client = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(*_TABLES)
    client.execute_many(
        sql.SQL(
            "INSERT INTO quiz_questions "
            "(number, question_id, topic, text, correct_answer, image_filename) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        ),
        [list(row) for row in _QUESTIONS],
    )
    yield client
    client.truncate(*_TABLES)


def _epoch() -> LabelingEpoch:
    return get_default_container().resolve(LabelingStackProvider).epoch


def _insert_embedding(client: PostgresClient, number: str, variant: str) -> None:
    question_id = client.fetch(
        sql.SQL("SELECT id FROM quiz_questions WHERE number = %s"), [number]
    )[0][0]
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_question_embeddings (quiz_question_id, variant, embedding_3_small) "
            "VALUES (%s, %s, %s::vector)"
        ),
        [question_id, variant, [0.0] * 1536],
    )


def _insert_labeling(client: PostgresClient, number: str, *, has_commas: bool) -> None:
    epoch = _epoch()
    run_id = client.fetch(
        sql.SQL(
            "INSERT INTO labeling_runs "
            "(judge_model, prompt_version, candidate_variant, dense_k, text_k, lexeme_fields, "
            " shuffle_seed, corpus_commit, corpus_comma_count, origin) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'batch') RETURNING id"
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
            3,
        ],
    )[0][0]
    question_id = client.fetch(
        sql.SQL("SELECT id FROM quiz_questions WHERE number = %s"), [number]
    )[0][0]
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_labelings "
            "(run_id, quiz_question_id, rationale, has_supporting_commas, created_at) "
            "VALUES (%s, %s, %s, %s, %s)"
        ),
        [run_id, question_id, "motivazione", has_commas, datetime.now(UTC)],
    )


@pytest.mark.integration
def test_a_proposal_is_reproducible_for_the_same_seed_and_index(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    first = api_client.get(
        "/quiz-questions/random", params={"seed": "abc", "index": 0}, headers=registered_headers
    )
    second = api_client.get(
        "/quiz-questions/random", params={"seed": "abc", "index": 0}, headers=registered_headers
    )

    assert first.status_code == 200
    assert first.json()["number"] == second.json()["number"]


@pytest.mark.integration
def test_a_proposal_never_leaks_the_answer(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    body = api_client.get(
        "/quiz-questions/random", params={"seed": "abc", "index": 0}, headers=registered_headers
    ).json()

    assert set(body) == {"number", "topic", "text", "image_url"}


@pytest.mark.integration
def test_an_illustrated_proposal_carries_a_callable_image_url(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    body = api_client.get("/quiz-questions/0001", headers=registered_headers).json()

    assert body["image_url"] == "/quiz-images/s0001.jpeg"


@pytest.mark.integration
def test_an_image_less_proposal_carries_a_null_url(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    assert (
        api_client.get("/quiz-questions/0003", headers=registered_headers).json()["image_url"]
        is None
    )


@pytest.mark.integration
def test_an_index_past_the_end_is_a_404(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.get(
        "/quiz-questions/random", params={"seed": "abc", "index": 3}, headers=registered_headers
    )

    assert response.status_code == 404


@pytest.mark.integration
def test_a_negative_index_is_rejected_as_a_validation_error(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.get(
        "/quiz-questions/random", params={"seed": "abc", "index": -1}, headers=registered_headers
    )

    assert response.status_code == 422


@pytest.mark.integration
def test_the_seed_and_index_are_required(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    assert api_client.get("/quiz-questions/random", headers=registered_headers).status_code == 422


@pytest.mark.integration
def test_the_topic_filter_is_honoured(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    body = api_client.get(
        "/quiz-questions/random",
        params={"seed": "abc", "index": 0, "topic": "velocità"},
        headers=registered_headers,
    ).json()

    assert body["topic"] == "velocità"


@pytest.mark.integration
def test_an_unknown_number_is_a_404(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    assert api_client.get("/quiz-questions/9999", headers=registered_headers).status_code == 404


@pytest.mark.integration
def test_the_topics_endpoint_is_not_shadowed_by_the_number_route(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.get("/quiz-questions/topics", headers=registered_headers)

    assert response.status_code == 200
    assert response.json()["topics"] == [
        {"topic": "segnaletica", "question_count": 2},
        {"topic": "velocità", "question_count": 1},
    ]


@pytest.mark.integration
def test_an_empty_bank_lists_no_topics_rather_than_404(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    bank.truncate(*_TABLES)

    response = api_client.get("/quiz-questions/topics", headers=registered_headers)

    assert response.status_code == 200
    assert response.json() == {"topics": []}


@pytest.mark.integration
def test_a_listed_topic_resolves_at_index_zero(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    topic = api_client.get("/quiz-questions/topics", headers=registered_headers).json()["topics"][
        0
    ]["topic"]

    response = api_client.get(
        "/quiz-questions/random",
        params={"seed": "abc", "index": 0, "topic": topic},
        headers=registered_headers,
    )

    assert response.status_code == 200


@pytest.mark.integration
def test_a_correct_answer_is_graded_true(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.post(
        "/quiz-questions/0001/check",
        json={"answer": True, "session_id": "test-session"},
        headers=registered_headers,
    )

    assert response.status_code == 200
    assert response.json()["correct"] is True


@pytest.mark.integration
def test_a_wrong_answer_is_graded_false(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    assert (
        api_client.post(
            "/quiz-questions/0001/check",
            json={"answer": False, "session_id": "test-session"},
            headers=registered_headers,
        ).json()["correct"]
        is False
    )


@pytest.mark.integration
def test_checking_an_unknown_number_is_a_404(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    assert (
        api_client.post(
            "/quiz-questions/9999/check",
            json={"answer": True, "session_id": "test-session"},
            headers=registered_headers,
        ).status_code
        == 404
    )


@pytest.mark.integration
def test_an_unlabeled_unembedded_question_advertises_unavailable(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    body = api_client.post(
        "/quiz-questions/0002/check",
        json={"answer": False, "session_id": "test-session"},
        headers=registered_headers,
    ).json()

    assert body["explanation_status"] == "unavailable"


@pytest.mark.integration
def test_an_embedded_but_unlabeled_question_advertises_uncached(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    _insert_embedding(bank, "0002", _epoch().candidate_variant)

    body = api_client.post(
        "/quiz-questions/0002/check",
        json={"answer": False, "session_id": "test-session"},
        headers=registered_headers,
    ).json()

    assert body["explanation_status"] == "uncached"


@pytest.mark.integration
def test_a_labeled_question_advertises_cached_without_an_embedding(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    _insert_labeling(bank, "0003", has_commas=True)

    body = api_client.post(
        "/quiz-questions/0003/check",
        json={"answer": True, "session_id": "test-session"},
        headers=registered_headers,
    ).json()

    assert body["explanation_status"] == "cached"


@pytest.mark.integration
def test_an_empty_verdict_advertises_unavailable_even_with_an_embedding(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    _insert_embedding(bank, "0003", _epoch().candidate_variant)
    _insert_labeling(bank, "0003", has_commas=False)

    body = api_client.post(
        "/quiz-questions/0003/check",
        json={"answer": True, "session_id": "test-session"},
        headers=registered_headers,
    ).json()

    assert body["explanation_status"] == "unavailable"


@pytest.mark.integration
def test_an_unregistered_caller_is_rejected_on_check(
    bank: PostgresClient, api_client: TestClient
) -> None:
    response = api_client.post(
        "/quiz-questions/0001/check",
        json={"answer": True},
        headers={"X-Telegram-User-Id": "999"},
    )

    assert response.status_code == 403


@pytest.mark.integration
def test_an_unregistered_caller_still_gets_provisioned(
    bank: PostgresClient, api_client: TestClient
) -> None:
    api_client.get("/quiz-questions/topics", headers={"X-Telegram-User-Id": "12345"})

    row = (
        get_default_container()
        .resolve(PostgresClientProvider)
        .client.fetch(sql.SQL("SELECT registered FROM users WHERE telegram_user_id = %s"), [12345])
    )
    assert row == [(False,)]


@pytest.mark.integration
def test_checking_an_answer_persists_it_with_the_session_id(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    api_client.post(
        "/quiz-questions/0001/check",
        json={"answer": True, "session_id": "seed-xyz"},
        headers=registered_headers,
    )

    row = bank.fetch(
        sql.SQL(
            "SELECT session_id, user_answer FROM quiz_answers "
            "JOIN users ON users.id = quiz_answers.user_id "
            "WHERE users.telegram_user_id = 1"
        )
    )
    assert row == [("seed-xyz", True)]


@pytest.mark.integration
def test_checking_the_same_question_twice_records_two_rows(
    bank: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    for _ in range(2):
        api_client.post(
            "/quiz-questions/0001/check",
            json={"answer": True, "session_id": "seed-xyz"},
            headers=registered_headers,
        )

    count = bank.fetch(sql.SQL("SELECT count(*) FROM quiz_answers"))[0][0]
    assert count == 2
