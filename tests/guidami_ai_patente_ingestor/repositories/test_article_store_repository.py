from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.knowledge import ArticleEntity
from guidami_ai_patente_ingestor.repositories import ArticleStoreRepository


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate("quiz_comma_labels", "article_commas", "articles")
        yield client
        client.truncate("quiz_comma_labels", "article_commas", "articles")


def _article(number: str, source: str = "cds") -> ArticleEntity:
    return ArticleEntity(
        source=source,  # type: ignore[arg-type]
        number=number,
        title=f"Articolo {number}",
        url=f"https://example.com/art-{number}",
        scraped_at=datetime(2026, 1, 1, tzinfo=UTC),
        is_repealed=False,
    )


@pytest.mark.integration
def test_bulk_insert_inserts_articles(client: PostgresClient) -> None:
    repository = ArticleStoreRepository("articles", client)

    repository.bulk_insert([_article("1"), _article("2")])

    rows = client.fetch(sql.SQL("SELECT number FROM articles ORDER BY id"))
    assert [row[0] for row in rows] == ["1", "2"]


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


@pytest.mark.integration
def test_upsert_updates_in_place_and_keeps_the_id(client: PostgresClient) -> None:
    repository = ArticleStoreRepository("articles", client)
    article_id = repository.upsert_returning_ids([_article("142")])[0]

    repository.upsert([_article("142").model_copy(update={"title": "Articolo 142 aggiornato"})])

    rows = client.fetch(sql.SQL("SELECT id, title FROM articles WHERE number = %s"), ["142"])
    assert len(rows) == 1, "re-upserting the same natural key must not insert a second row"
    assert rows[0][0] == article_id, "the id must stay stable across an upsert of the same key"
    assert rows[0][1] == "Articolo 142 aggiornato"


@pytest.mark.integration
def test_delete_missing_removes_only_absent_numbers_of_that_source(
    client: PostgresClient,
) -> None:
    repository = ArticleStoreRepository("articles", client)
    repository.upsert_returning_ids(
        [_article("1", source="cds"), _article("2", source="cds"), _article("1", source="cap")]
    )

    repository.delete_missing("cds", [_article("1", source="cds")])

    rows = client.fetch(sql.SQL("SELECT source, number FROM articles ORDER BY source, number"))
    assert {(row[0], row[1]) for row in rows} == {("cap", "1"), ("cds", "1")}
