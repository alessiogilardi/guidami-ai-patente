from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from commons.repositories.db import CorpusReadRepository


def _vector(dimension: int, hot_index: int) -> list[float]:
    """Builds a 1536-dim one-hot vector, used so cosine distance is unambiguous."""
    vector = [0.0] * dimension
    vector[hot_index] = 1.0
    return vector


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate("article_commas", "articles")
        yield client
        client.truncate("article_commas", "articles")


def _insert_article(client: PostgresClient, source: str, number: str, title: str) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO articles (source, number, title, url, scraped_at) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        [source, number, title, "https://example.test", datetime.now(UTC)],
    )
    return rows[0][0]


def _insert_comma(
    client: PostgresClient,
    article_id: int,
    comma_number: str,
    text: str,
    embedding: list[float] | None,
) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO article_commas (article_id, comma_number, position, text, embedding) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        [article_id, comma_number, 0, text, embedding],
    )
    return rows[0][0]


@pytest.mark.integration
def test_dense_top_k_returns_source_qualified_commas(client: PostgresClient) -> None:
    cds_article_id = _insert_article(client, "cds", "43", "Segnaletica CdS")
    reg_article_id = _insert_article(client, "reg", "43", "Segnaletica Regolamento")
    _insert_comma(client, cds_article_id, "1", "Testo cds.", _vector(1536, 0))
    _insert_comma(client, reg_article_id, "1", "Testo reg.", _vector(1536, 1))

    repository = CorpusReadRepository("articles", "article_commas", client)
    query_vector = _vector(1536, 0)

    results = repository.dense_top_k(query_vector, k=2)

    assert len(results) == 2
    assert results[0].distance <= results[1].distance
    assert results[0].source == "cds"
    assert all(comma.article_title for comma in results)


@pytest.mark.integration
def test_random_top_k_excludes_unembedded_commas(client: PostgresClient) -> None:
    article_id = _insert_article(client, "cds", "1", "Titolo")
    _insert_comma(client, article_id, "1", "Comma senza embedding.", None)

    repository = CorpusReadRepository("articles", "article_commas", client)

    for seed_key in ("seed-a", "seed-b", "seed-c"):
        results = repository.random_top_k(k=5, seed_key=seed_key)
        assert all(comma.comma_number != "1" for comma in results)
