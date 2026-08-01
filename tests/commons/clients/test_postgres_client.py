from collections.abc import Iterator

import pytest
from psycopg import sql
from pydantic import SecretStr

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig


@pytest.fixture
def client() -> Iterator[PostgresClient]:
    config = PostgresConnectionConfig(
        host="localhost",
        port=5432,
        user="guidami",
        password=SecretStr("guidami"),
        dbname="guidami_ai_patente",
    )
    with PostgresClient(config) as client:
        client.truncate("article_commas", "articles")
        yield client
        client.truncate("article_commas", "articles")


_INSERT_ARTICLE_RETURNING_ID = sql.SQL(
    "INSERT INTO articles (source, number, title, url, is_repealed) "
    "VALUES (%s, %s, %s, %s, %s) RETURNING id"
)

_INSERT_ARTICLE = sql.SQL(
    "INSERT INTO articles (source, number, title, url, is_repealed) VALUES (%s, %s, %s, %s, %s)"
)

_INSERT_ARTICLE_COMMA = sql.SQL(
    "INSERT INTO article_commas "
    "(article_id, comma_number, position, text, is_repealed, embedding) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)


_EMBEDDING_DIM = 1536


@pytest.mark.integration
def test_execute_many_and_fetch_round_trip_with_pgvector(client: PostgresClient) -> None:
    embedding = [1.0, *([0.0] * (_EMBEDDING_DIM - 1))]

    article_rows = client.fetch(
        _INSERT_ARTICLE_RETURNING_ID, ["cds", "1", "Articolo 1", "https://example.com/1", False]
    )
    article_id = article_rows[0][0]

    client.execute_many(
        _INSERT_ARTICLE_COMMA,
        [(article_id, "1", 0, "Testo", False, embedding)],
    )

    rows = client.fetch(sql.SQL("SELECT comma_number, embedding FROM article_commas"))

    assert rows[0][0] == "1"
    assert list(rows[0][1]) == embedding


@pytest.mark.integration
def test_truncate_empties_table(client: PostgresClient) -> None:
    client.execute_many(
        _INSERT_ARTICLE,
        [("cds", "1", "Articolo 1", "https://example.com/1", False)],
    )

    # `articles` is FK-referenced by `article_commas`, so Postgres refuses a bare
    # single-table TRUNCATE on it (regardless of whether article_commas has rows) —
    # both names must be named in one combined statement, see PostgresClient.truncate.
    client.truncate("article_commas", "articles")

    rows = client.fetch(sql.SQL("SELECT number FROM articles"))
    assert rows == []


@pytest.mark.integration
def test_truncate_accepts_multiple_tables_empties_all_of_them(client: PostgresClient) -> None:
    article_rows = client.fetch(
        _INSERT_ARTICLE_RETURNING_ID, ["cds", "1", "Articolo 1", "https://example.com/1", False]
    )
    article_id = article_rows[0][0]
    client.execute_many(
        _INSERT_ARTICLE_COMMA,
        [(article_id, "1", 0, "Testo", False, None)],
    )

    client.truncate("article_commas", "articles")

    assert client.fetch(sql.SQL("SELECT id FROM article_commas")) == []
    assert client.fetch(sql.SQL("SELECT id FROM articles")) == []


@pytest.mark.integration
def test_execute_runs_parametrized_statement(client: PostgresClient) -> None:
    client.execute_many(
        _INSERT_ARTICLE,
        [
            ("cds", "1", "Articolo 1", "https://example.com/1", False),
            ("cap", "2", "Articolo 2", "https://example.com/2", False),
        ],
    )

    client.execute(sql.SQL("DELETE FROM articles WHERE source = %s"), ["cds"])

    rows = client.fetch(sql.SQL("SELECT source FROM articles"))
    assert [row[0] for row in rows] == ["cap"]
