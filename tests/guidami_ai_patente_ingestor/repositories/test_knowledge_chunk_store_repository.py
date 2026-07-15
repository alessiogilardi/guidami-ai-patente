from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.knowledge import KnowledgeChunk
from guidami_ai_patente_ingestor.repositories import KnowledgeChunkStoreRepository


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


_EMBEDDING_DIM = 1536


def _embedding() -> list[float]:
    return [1.0, *([0.0] * (_EMBEDDING_DIM - 1))]


def _chunk(article_number: str, source: str = "cds") -> KnowledgeChunk:
    return KnowledgeChunk(
        source=source,  # type: ignore[arg-type]
        article_number=article_number,
        article_title=f"Articolo {article_number}",
        comma_index=1,
        chunk_text=f"Testo dell'articolo {article_number}",
        is_repealed=False,
        source_url=f"https://example.com/art-{article_number}",
        embedding=_embedding(),
    )


@pytest.mark.integration
def test_bulk_insert_inserts_chunks(client: PostgresClient) -> None:
    repository = KnowledgeChunkStoreRepository("knowledge_chunks", client)

    repository.bulk_insert([_chunk("1"), _chunk("2")])

    rows = client.fetch(sql.SQL("SELECT article_number FROM knowledge_chunks ORDER BY id"))
    assert [row[0] for row in rows] == ["1", "2"]


@pytest.mark.integration
def test_bulk_insert_with_empty_list_is_noop(client: PostgresClient) -> None:
    repository = KnowledgeChunkStoreRepository("knowledge_chunks", client)

    repository.bulk_insert([])

    rows = client.fetch(sql.SQL("SELECT article_number FROM knowledge_chunks"))
    assert rows == []


@pytest.mark.integration
def test_delete_source_removes_only_that_source(client: PostgresClient) -> None:
    """delete_source removes only chunks of the given source, others survive."""
    repository = KnowledgeChunkStoreRepository("knowledge_chunks", client)
    repository.bulk_insert([_chunk("1", source="cds"), _chunk("2", source="cap")])

    repository.delete_source("cds")

    rows = client.fetch(sql.SQL("SELECT source FROM knowledge_chunks"))
    assert [row[0] for row in rows] == ["cap"]


@pytest.mark.integration
def test_row_count_and_table_exists(client: PostgresClient) -> None:
    """table_exists/row_count read the real table state for an existing table."""
    repository = KnowledgeChunkStoreRepository("knowledge_chunks", client)
    repository.bulk_insert([_chunk("1"), _chunk("2")])

    assert repository.table_exists() is True
    assert repository.row_count() == 2


@pytest.mark.integration
def test_table_exists_is_false_for_missing_table(client: PostgresClient) -> None:
    """A non-existent table name is reported as absent without issuing a count."""
    repository = KnowledgeChunkStoreRepository("definitely_not_a_real_table", client)

    assert repository.table_exists() is False
