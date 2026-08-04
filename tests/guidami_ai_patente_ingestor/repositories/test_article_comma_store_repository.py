from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.knowledge import ArticleCommaEntity, ArticleEntity
from guidami_ai_patente_ingestor.repositories import (
    ArticleCommaStoreRepository,
    ArticleStoreRepository,
)


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
        client.truncate("article_commas", "articles")
        yield client
        client.truncate("article_commas", "articles")


def _insert_article(client: PostgresClient, number: str, source: str) -> int:
    article = ArticleEntity(
        source=source,  # type: ignore[arg-type]
        number=number,
        title=f"Articolo {number}",
        url=f"https://example.com/art-{number}",
        scraped_at=datetime(2026, 1, 1, tzinfo=UTC),
        is_repealed=False,
    )
    ids = ArticleStoreRepository("articles", client).bulk_insert_returning_ids([article])
    return ids[0]


def _comma(article_id: int, comma_number: str = "1") -> ArticleCommaEntity:
    return ArticleCommaEntity(
        article_id=article_id,
        comma_number=comma_number,
        position=0,
        text=f"Testo del comma {comma_number}",
        is_repealed=False,
        embedding=None,
    )


@pytest.mark.integration
def test_bulk_insert_inserts_commas(client: PostgresClient) -> None:
    article_id = _insert_article(client, "1", "cds")
    repository = ArticleCommaStoreRepository("article_commas", client)

    repository.bulk_insert([_comma(article_id, "1"), _comma(article_id, "2")])

    rows = client.fetch(sql.SQL("SELECT comma_number FROM article_commas ORDER BY id"))
    assert [row[0] for row in rows] == ["1", "2"]


@pytest.mark.integration
def test_bulk_insert_stores_embedding_vector(client: PostgresClient) -> None:
    article_id = _insert_article(client, "1", "cds")
    repository = ArticleCommaStoreRepository("article_commas", client)
    embedding = [1.0, *([0.0] * 1535)]

    repository.bulk_insert(
        [
            ArticleCommaEntity(
                article_id=article_id,
                comma_number="1",
                position=0,
                text="Testo",
                is_repealed=False,
                embedding=embedding,
            )
        ]
    )

    rows = client.fetch(sql.SQL("SELECT embedding FROM article_commas"))
    assert list(rows[0][0]) == embedding


@pytest.mark.integration
def test_delete_source_removes_only_that_sources_commas(client: PostgresClient) -> None:
    cds_article_id = _insert_article(client, "1", "cds")
    cap_article_id = _insert_article(client, "2", "cap")
    repository = ArticleCommaStoreRepository("article_commas", client)
    repository.bulk_insert([_comma(cds_article_id, "1"), _comma(cap_article_id, "1")])

    repository.delete_source("cds")

    rows = client.fetch(
        sql.SQL("SELECT a.source FROM article_commas c JOIN articles a ON a.id = c.article_id")
    )
    assert [row[0] for row in rows] == ["cap"]
