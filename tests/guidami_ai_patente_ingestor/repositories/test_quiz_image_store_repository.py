from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.quiz import QuizImageEntity
from guidami_ai_patente_ingestor.repositories import QuizImageStoreRepository


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate("quiz_images")
        yield client
        client.truncate("quiz_images")


def _image(filename: str, description: str | None = None) -> QuizImageEntity:
    return QuizImageEntity(filename=filename, description=description)


@pytest.mark.integration
def test_upsert_then_reupsert_keeps_one_row_per_filename(client: PostgresClient) -> None:
    repository = QuizImageStoreRepository("quiz_images", client)
    entity_1 = _image("abc.jpeg", description="Segnale di stop.")
    entity_2 = _image("abc.jpeg", description="Segnale di divieto di sosta.")

    repository.upsert([entity_1])
    repository.upsert([entity_2])

    rows = client.fetch(sql.SQL("SELECT filename, description FROM quiz_images"))
    assert rows == [("abc.jpeg", "Segnale di divieto di sosta.")], (
        "the later upsert must win, keeping exactly one row for the shared filename"
    )


@pytest.mark.integration
def test_upsert_with_empty_list_is_noop(client: PostgresClient) -> None:
    repository = QuizImageStoreRepository("quiz_images", client)

    repository.upsert([])

    rows = client.fetch(sql.SQL("SELECT filename FROM quiz_images"))
    assert rows == []
