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
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
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
def test_reupserting_a_parent_keeps_its_commas(client: PostgresClient) -> None:
    article_repository = ArticleStoreRepository("articles", client)
    comma_repository = ArticleCommaStoreRepository("article_commas", client)
    article_id = article_repository.upsert_returning_ids([_article("142")])[0]
    comma_repository.upsert([_comma(article_id, "1")])

    article_repository.upsert(
        [_article("142").model_copy(update={"title": "Articolo 142 aggiornato"})]
    )

    rows = client.fetch(sql.SQL("SELECT article_id, comma_number FROM article_commas"))
    assert [(row[0], row[1]) for row in rows] == [(article_id, "1")], (
        "the comma must survive its parent's upsert, still referencing the same article_id"
    )


@pytest.mark.integration
def test_delete_missing_keeps_present_commas_and_other_articles(client: PostgresClient) -> None:
    first_id = _insert_article(client, "1", "cds")
    second_id = _insert_article(client, "2", "cds")
    repository = ArticleCommaStoreRepository("article_commas", client)
    repository.upsert([_comma(first_id, "1"), _comma(first_id, "2"), _comma(second_id, "1")])

    repository.delete_missing([first_id], [_comma(first_id, "1")])

    rows = client.fetch(
        sql.SQL(
            "SELECT article_id, comma_number FROM article_commas ORDER BY article_id, comma_number"
        )
    )
    assert [(row[0], row[1]) for row in rows] == [(first_id, "1"), (second_id, "1")]
