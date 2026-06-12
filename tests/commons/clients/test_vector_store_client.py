from collections.abc import Iterator

import pytest

from commons.clients import VectorStoreClient
from commons.configs import VectorStoreConfig
from commons.models.knowledge import KnowledgeChunk

DATABASE_URL = "postgresql://guidami:guidami@localhost:5432/guidami_ai_patente"


@pytest.fixture
def client() -> Iterator[VectorStoreClient]:
    with VectorStoreClient(VectorStoreConfig(database_url=DATABASE_URL)) as client:
        client.truncate()
        yield client
        client.truncate()


def _chunk(
    article_number: str, embedding: list[float], is_repealed: bool = False
) -> KnowledgeChunk:
    return KnowledgeChunk(
        source="cds",
        article_number=article_number,
        article_title=f"Articolo {article_number}",
        comma_index=1,
        chunk_text=f"Testo dell'articolo {article_number}",
        is_repealed=is_repealed,
        source_url=f"https://example.com/art-{article_number}",
        embedding=embedding,
    )


@pytest.mark.integration
def test_bulk_insert_then_similarity_search_returns_closest_first(
    client: VectorStoreClient,
) -> None:
    close = _chunk("1", embedding=[1.0, 0.0, *([0.0] * 382)])
    far = _chunk("2", embedding=[0.0, 1.0, *([0.0] * 382)])
    client.bulk_insert([close, far])

    results = client.similarity_search(embedding=[1.0, 0.0, *([0.0] * 382)], top_k=2)

    assert [result.chunk.article_number for result in results] == ["1", "2"]
    assert results[0].score > results[1].score


@pytest.mark.integration
def test_similarity_search_filters_by_source(client: VectorStoreClient) -> None:
    cds_chunk = _chunk("1", embedding=[1.0, *([0.0] * 383)])
    cap_chunk = KnowledgeChunk(
        source="cap",
        article_number="1",
        article_title="Articolo CAP 1",
        comma_index=1,
        chunk_text="Testo CAP",
        is_repealed=False,
        source_url="https://example.com/cap-1",
        embedding=[1.0, *([0.0] * 383)],
    )
    client.bulk_insert([cds_chunk, cap_chunk])

    results = client.similarity_search(embedding=[1.0, *([0.0] * 383)], top_k=10, source="cap")

    assert len(results) == 1
    assert results[0].chunk.source == "cap"


@pytest.mark.integration
def test_truncate_empties_table(client: VectorStoreClient) -> None:
    client.bulk_insert([_chunk("1", embedding=[1.0, *([0.0] * 383)])])

    client.truncate()

    results = client.similarity_search(embedding=[1.0, *([0.0] * 383)], top_k=10)
    assert results == []
