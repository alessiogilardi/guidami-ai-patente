from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.knowledge import ArticleEntity
from guidami_ai_patente_ingestor.repositories import ArticleStoreRepository


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


def _article(number: str, source: str = "cds") -> ArticleEntity:
    return ArticleEntity(
        source=source,  # type: ignore[arg-type]
        number=number,
        title=f"Articolo {number}",
        url=f"https://example.com/art-{number}",
        is_repealed=False,
    )


@pytest.mark.integration
def test_bulk_insert_inserts_articles(client: PostgresClient) -> None:
    repository = ArticleStoreRepository("articles", client)

    repository.bulk_insert([_article("1"), _article("2")])

    rows = client.fetch(sql.SQL("SELECT number FROM articles ORDER BY id"))
    assert [row[0] for row in rows] == ["1", "2"]


@pytest.mark.integration
def test_delete_source_removes_only_that_source(client: PostgresClient) -> None:
    repository = ArticleStoreRepository("articles", client)
    repository.bulk_insert([_article("1", source="cds"), _article("2", source="cap")])

    repository.delete_source("cds")

    rows = client.fetch(sql.SQL("SELECT source FROM articles"))
    assert [row[0] for row in rows] == ["cap"]


@pytest.mark.integration
def test_bulk_insert_returning_ids_preserves_input_order(client: PostgresClient) -> None:
    repository = ArticleStoreRepository("articles", client)
    articles = [_article("142"), _article("143")]

    ids = repository.bulk_insert_returning_ids(articles)

    assert len(ids) == 2
    assert len(set(ids)) == 2

    fetched = client.fetch(sql.SQL("SELECT id, number FROM articles ORDER BY id"))
    assert [row[0] for row in fetched] == ids
    assert [row[1] for row in fetched] == ["142", "143"]
