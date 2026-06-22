from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig


@pytest.fixture
def client() -> Iterator[PostgresClient]:
    config = PostgresConnectionConfig(
        host="localhost",
        port=5432,
        user="guidami",
        password="guidami",
        dbname="guidami_ai_patente",
    )
    with PostgresClient(config) as client:
        client.truncate("knowledge_chunks")
        yield client
        client.truncate("knowledge_chunks")


_INSERT_CHUNK = sql.SQL(
    "INSERT INTO knowledge_chunks "
    "(source, article_number, article_title, comma_index, chunk_text, "
    "is_repealed, source_url, embedding) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
)


_EMBEDDING_DIM = 1536


@pytest.mark.integration
def test_execute_many_and_fetch_round_trip_with_pgvector(client: PostgresClient) -> None:
    embedding = [1.0, *([0.0] * (_EMBEDDING_DIM - 1))]
    client.execute_many(
        _INSERT_CHUNK,
        [("cds", "1", "Articolo 1", 1, "Testo", False, "https://example.com/1", embedding)],
    )

    rows = client.fetch(sql.SQL("SELECT article_number, embedding FROM knowledge_chunks"))

    assert rows[0][0] == "1"
    assert list(rows[0][1]) == embedding


@pytest.mark.integration
def test_truncate_empties_table(client: PostgresClient) -> None:
    embedding = [1.0, *([0.0] * (_EMBEDDING_DIM - 1))]
    client.execute_many(
        _INSERT_CHUNK,
        [("cds", "1", "Articolo 1", 1, "Testo", False, "https://example.com/1", embedding)],
    )

    client.truncate("knowledge_chunks")

    rows = client.fetch(sql.SQL("SELECT article_number FROM knowledge_chunks"))
    assert rows == []


@pytest.mark.integration
def test_execute_runs_parametrized_statement(client: PostgresClient) -> None:
    embedding = [1.0, *([0.0] * (_EMBEDDING_DIM - 1))]
    client.execute_many(
        _INSERT_CHUNK,
        [
            ("cds", "1", "Articolo 1", 1, "Testo", False, "https://example.com/1", embedding),
            ("cap", "2", "Articolo 2", 1, "Testo", False, "https://example.com/2", embedding),
        ],
    )

    client.execute(sql.SQL("DELETE FROM knowledge_chunks WHERE source = %s"), ["cds"])

    rows = client.fetch(sql.SQL("SELECT source FROM knowledge_chunks"))
    assert [row[0] for row in rows] == ["cap"]
