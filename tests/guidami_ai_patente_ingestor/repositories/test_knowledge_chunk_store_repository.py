from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from commons.entities.knowledge import KnowledgeChunk
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


def _chunk(article_number: str, embedding: list[float]) -> KnowledgeChunk:
    return KnowledgeChunk(
        source="cds",
        article_number=article_number,
        article_title=f"Articolo {article_number}",
        comma_index=1,
        chunk_text=f"Testo dell'articolo {article_number}",
        is_repealed=False,
        source_url=f"https://example.com/art-{article_number}",
        embedding=embedding,
    )


@pytest.mark.integration
def test_bulk_insert_inserts_chunks(client: PostgresClient) -> None:
    repository = KnowledgeChunkStoreRepository(client, "knowledge_chunks")

    repository.bulk_insert(
        [_chunk("1", [1.0, *([0.0] * 383)]), _chunk("2", [0.0, *([0.0] * 383)])]
    )

    rows = client.fetch(sql.SQL("SELECT article_number FROM knowledge_chunks ORDER BY id"))
    assert [row[0] for row in rows] == ["1", "2"]


@pytest.mark.integration
def test_bulk_insert_with_empty_list_is_noop(client: PostgresClient) -> None:
    repository = KnowledgeChunkStoreRepository(client, "knowledge_chunks")

    repository.bulk_insert([])

    rows = client.fetch(sql.SQL("SELECT article_number FROM knowledge_chunks"))
    assert rows == []


@pytest.mark.integration
def test_truncate_empties_table(client: PostgresClient) -> None:
    repository = KnowledgeChunkStoreRepository(client, "knowledge_chunks")
    repository.bulk_insert([_chunk("1", [1.0, *([0.0] * 383)])])

    repository.truncate()

    rows = client.fetch(sql.SQL("SELECT article_number FROM knowledge_chunks"))
    assert rows == []
