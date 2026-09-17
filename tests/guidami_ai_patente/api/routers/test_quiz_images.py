"""End-to-end tests for the image endpoint (FR-12, AD-24)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from pywire import get_default_container

from commons.clients import PostgresClient
from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig

_REFERENCED = "000b9ec4803628ffc83403efb710b16e.jpeg"
_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "labeling_runs",
    "quiz_question_embeddings",
    "quiz_answers",
    "quiz_questions",
)


@pytest.fixture
def bank_with_image(api_client: TestClient) -> Iterator[PostgresClient]:
    client = get_default_container().resolve(PostgresClientProvider).client
    client.truncate(*_TABLES)
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_questions "
            "(number, question_id, topic, text, correct_answer, image_filename) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        ),
        ["0001", 1, "segnaletica", "Domanda?", True, _REFERENCED],
    )
    yield client
    client.truncate(*_TABLES)


@pytest.mark.integration
def test_a_referenced_image_is_served_with_its_bytes_and_type(
    bank_with_image: PostgresClient,
    api_client: TestClient,
    app_config: AppConfig,
    registered_headers: dict[str, str],
) -> None:
    response = api_client.get(f"/quiz-images/{_REFERENCED}", headers=registered_headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == (app_config.quiz_images_dir / _REFERENCED).read_bytes()


@pytest.mark.integration
def test_an_unreferenced_name_is_a_404(
    bank_with_image: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    assert (
        api_client.get("/quiz-images/never-referenced.png", headers=registered_headers).status_code
        == 404
    )


@pytest.mark.integration
def test_a_traversal_attempt_is_a_404_and_leaks_nothing(
    bank_with_image: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    response = api_client.get("/quiz-images/..%2F..%2F.env", headers=registered_headers)

    assert response.status_code == 404
    assert b"POSTGRES" not in response.content


@pytest.mark.integration
def test_the_url_a_proposal_returns_is_directly_callable(
    bank_with_image: PostgresClient, api_client: TestClient, registered_headers: dict[str, str]
) -> None:
    image_url = api_client.get("/quiz-questions/0001", headers=registered_headers).json()[
        "image_url"
    ]

    assert api_client.get(image_url, headers=registered_headers).status_code == 200
