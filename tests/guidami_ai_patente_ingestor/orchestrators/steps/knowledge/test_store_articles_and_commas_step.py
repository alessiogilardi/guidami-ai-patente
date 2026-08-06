"""Tests for StoreArticlesAndCommasStep (upsert + reconciliation of articles + commas)."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from flowstep import FlowContext
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.knowledge import ArticleCommaEntity, ArticleEntity
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableArticleComma
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import (
    StoreArticlesAndCommasStep,
)
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


def _article(number: str, source: str = "cds") -> ArticleEntity:
    return ArticleEntity(
        source=source,  # type: ignore[arg-type]
        number=number,
        title=f"Articolo {number}",
        url=f"https://example.com/art-{number}",
        scraped_at=datetime(2026, 1, 1, tzinfo=UTC),
        is_repealed=False,
    )


def _embeddable_comma(article_number: str, source: str = "cds") -> EmbeddableArticleComma:
    return EmbeddableArticleComma(
        source=source,
        article_number=article_number,
        article_title=f"Articolo {article_number}",
        comma_number="1",
        position=0,
        text="Testo del comma",
        is_repealed=False,
        embedding=None,
    )


@pytest.mark.integration
def test_store_writes_articles_then_resolves_comma_article_id(client: PostgresClient) -> None:
    article_repository = ArticleStoreRepository("articles", client)
    article_comma_repository = ArticleCommaStoreRepository("article_commas", client)
    context = FlowContext(
        {
            context_keys.ARTICLE_ENTITIES: [_article("142")],
            context_keys.EMBEDDABLE_ARTICLE_COMMAS: [_embeddable_comma("142")],
        }
    )
    step = StoreArticlesAndCommasStep(
        "store_articles_and_commas", "cds", article_repository, article_comma_repository
    )

    step.execute(context)

    article_id = client.fetch(sql.SQL("SELECT id FROM articles WHERE number = %s"), ["142"])[0][0]
    comma_article_id = client.fetch(sql.SQL("SELECT article_id FROM article_commas"))[0][0]
    assert comma_article_id == article_id, (
        "the comma row's article_id must be the DB-generated id of the inserted article, "
        "not a hardcoded/placeholder value"
    )


@pytest.mark.integration
def test_store_replaces_only_target_source(client: PostgresClient) -> None:
    article_repository = ArticleStoreRepository("articles", client)
    article_comma_repository = ArticleCommaStoreRepository("article_commas", client)

    # Pre-seed a "cap" article + comma directly through the repositories.
    cap_article_ids = article_repository.upsert_returning_ids([_article("1", source="cap")])
    article_comma_repository.upsert(
        [
            ArticleCommaEntity(
                article_id=cap_article_ids[0],
                comma_number="1",
                position=0,
                text="Testo cap",
                is_repealed=False,
                embedding=None,
            )
        ]
    )

    context = FlowContext(
        {
            context_keys.ARTICLE_ENTITIES: [_article("142", source="cds")],
            context_keys.EMBEDDABLE_ARTICLE_COMMAS: [_embeddable_comma("142", source="cds")],
        }
    )
    step = StoreArticlesAndCommasStep(
        "store_articles_and_commas", "cds", article_repository, article_comma_repository
    )

    step.execute(context)
    step.execute(context)  # re-run for the same source: must not duplicate

    cap_rows = client.fetch(sql.SQL("SELECT source FROM articles WHERE source = 'cap'"))
    assert len(cap_rows) == 1, "cap rows must be untouched by a cds-source run"

    cds_rows = client.fetch(sql.SQL("SELECT number FROM articles WHERE source = 'cds'"))
    assert [row[0] for row in cds_rows] == ["142"], (
        "cds rows must reflect only the new data, no duplicates across runs"
    )


@pytest.mark.integration
def test_store_removes_an_article_that_vanished_from_the_layer(client: PostgresClient) -> None:
    """Pins FR-2's end state across a T-4 refactor.

    Passes already today (delete_source + reinsert reaches the same end state); it
    exists to guard against a later regression to pure upsert without reconciliation,
    not to drive T-4.
    """
    article_repository = ArticleStoreRepository("articles", client)
    article_comma_repository = ArticleCommaStoreRepository("article_commas", client)
    step = StoreArticlesAndCommasStep(
        "store_articles_and_commas", "cds", article_repository, article_comma_repository
    )
    first_context = FlowContext(
        {
            context_keys.ARTICLE_ENTITIES: [_article("1"), _article("2")],
            context_keys.EMBEDDABLE_ARTICLE_COMMAS: [
                _embeddable_comma("1"),
                _embeddable_comma("2"),
            ],
        }
    )
    step.execute(first_context)

    second_context = FlowContext(
        {
            context_keys.ARTICLE_ENTITIES: [_article("1")],
            context_keys.EMBEDDABLE_ARTICLE_COMMAS: [_embeddable_comma("1")],
        }
    )
    step.execute(second_context)

    remaining = client.fetch(sql.SQL("SELECT id, number FROM articles WHERE source = 'cds'"))
    assert [row[1] for row in remaining] == ["1"]
    remaining_article_id = remaining[0][0]

    comma_article_ids = client.fetch(sql.SQL("SELECT article_id FROM article_commas"))
    assert [row[0] for row in comma_article_ids] == [remaining_article_id], (
        "no article_commas row may still reference the removed article's id"
    )
