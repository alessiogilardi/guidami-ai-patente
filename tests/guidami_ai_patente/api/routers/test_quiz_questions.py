"""End-to-end tests for the no-LLM quiz endpoints (FR-1, FR-2, FR-3, FR-4, FR-16)."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import LabelingStackProvider, PostgresClientProvider
from labeling.models import LabelingEpoch

_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
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
    bank: PostgresClient, api_client: TestClient
) -> None:
    first = api_client.get("/quiz-questions/random", params={"seed": "abc", "index": 0})
    second = api_client.get("/quiz-questions/random", params={"seed": "abc", "index": 0})

    assert first.status_code == 200
    assert first.json()["number"] == second.json()["number"]


@pytest.mark.integration
def test_a_proposal_never_leaks_the_answer(bank: PostgresClient, api_client: TestClient) -> None:
    body = api_client.get("/quiz-questions/random", params={"seed": "abc", "index": 0}).json()

    assert set(body) == {"number", "topic", "text", "image_url"}


@pytest.mark.integration
def test_an_illustrated_proposal_carries_a_callable_image_url(
    bank: PostgresClient, api_client: TestClient
) -> None:
    body = api_client.get("/quiz-questions/0001").json()

    assert body["image_url"] == "/quiz-images/s0001.jpeg"


@pytest.mark.integration
def test_an_image_less_proposal_carries_a_null_url(
    bank: PostgresClient, api_client: TestClient
) -> None:
    assert api_client.get("/quiz-questions/0003").json()["image_url"] is None


@pytest.mark.integration
def test_an_index_past_the_end_is_a_404(bank: PostgresClient, api_client: TestClient) -> None:
    response = api_client.get("/quiz-questions/random", params={"seed": "abc", "index": 3})

    assert response.status_code == 404


@pytest.mark.integration
def test_a_negative_index_is_rejected_as_a_validation_error(
    bank: PostgresClient, api_client: TestClient
) -> None:
    response = api_client.get("/quiz-questions/random", params={"seed": "abc", "index": -1})

    assert response.status_code == 422


@pytest.mark.integration
def test_the_seed_and_index_are_required(bank: PostgresClient, api_client: TestClient) -> None:
    assert api_client.get("/quiz-questions/random").status_code == 422


@pytest.mark.integration
def test_the_topic_filter_is_honoured(bank: PostgresClient, api_client: TestClient) -> None:
    body = api_client.get(
        "/quiz-questions/random", params={"seed": "abc", "index": 0, "topic": "velocità"}
    ).json()

    assert body["topic"] == "velocità"


@pytest.mark.integration
def test_an_unknown_number_is_a_404(bank: PostgresClient, api_client: TestClient) -> None:
    assert api_client.get("/quiz-questions/9999").status_code == 404


@pytest.mark.integration
def test_the_topics_endpoint_is_not_shadowed_by_the_number_route(
    bank: PostgresClient, api_client: TestClient
) -> None:
    response = api_client.get("/quiz-questions/topics")

    assert response.status_code == 200
    assert response.json()["topics"] == [
        {"topic": "segnaletica", "question_count": 2},
        {"topic": "velocità", "question_count": 1},
    ]


@pytest.mark.integration
def test_an_empty_bank_lists_no_topics_rather_than_404(
    bank: PostgresClient, api_client: TestClient
) -> None:
    bank.truncate(*_TABLES)

    response = api_client.get("/quiz-questions/topics")

    assert response.status_code == 200
    assert response.json() == {"topics": []}


@pytest.mark.integration
def test_a_listed_topic_resolves_at_index_zero(
    bank: PostgresClient, api_client: TestClient
) -> None:
    topic = api_client.get("/quiz-questions/topics").json()["topics"][0]["topic"]

    response = api_client.get(
        "/quiz-questions/random", params={"seed": "abc", "index": 0, "topic": topic}
    )

    assert response.status_code == 200


@pytest.mark.integration
def test_a_correct_answer_is_graded_true(bank: PostgresClient, api_client: TestClient) -> None:
    response = api_client.post("/quiz-questions/0001/check", json={"answer": True})

    assert response.status_code == 200
    assert response.json()["correct"] is True


@pytest.mark.integration
def test_a_wrong_answer_is_graded_false(bank: PostgresClient, api_client: TestClient) -> None:
    assert (
        api_client.post("/quiz-questions/0001/check", json={"answer": False}).json()["correct"]
        is False
    )


@pytest.mark.integration
def test_checking_an_unknown_number_is_a_404(bank: PostgresClient, api_client: TestClient) -> None:
    assert api_client.post("/quiz-questions/9999/check", json={"answer": True}).status_code == 404


@pytest.mark.integration
def test_an_unlabeled_unembedded_question_advertises_unavailable(
    bank: PostgresClient, api_client: TestClient
) -> None:
    body = api_client.post("/quiz-questions/0002/check", json={"answer": False}).json()

    assert body["explanation_status"] == "unavailable"


@pytest.mark.integration
def test_an_embedded_but_unlabeled_question_advertises_uncached(
    bank: PostgresClient, api_client: TestClient
) -> None:
    _insert_embedding(bank, "0002", _epoch().candidate_variant)

    body = api_client.post("/quiz-questions/0002/check", json={"answer": False}).json()

    assert body["explanation_status"] == "uncached"


@pytest.mark.integration
def test_a_labeled_question_advertises_cached_without_an_embedding(
    bank: PostgresClient, api_client: TestClient
) -> None:
    _insert_labeling(bank, "0003", has_commas=True)

    body = api_client.post("/quiz-questions/0003/check", json={"answer": True}).json()

    assert body["explanation_status"] == "cached"


@pytest.mark.integration
def test_an_empty_verdict_advertises_unavailable_even_with_an_embedding(
    bank: PostgresClient, api_client: TestClient
) -> None:
    _insert_embedding(bank, "0003", _epoch().candidate_variant)
    _insert_labeling(bank, "0003", has_commas=False)

    body = api_client.post("/quiz-questions/0003/check", json={"answer": True}).json()

    assert body["explanation_status"] == "unavailable"
