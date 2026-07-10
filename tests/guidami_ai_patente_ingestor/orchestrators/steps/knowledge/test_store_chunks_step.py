"""Tests for StoreChunksStep (per-source full-reload)."""

from unittest.mock import MagicMock, call

from flowstep import FlowContext

from domain.entities.knowledge import KnowledgeChunk
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import StoreChunksStep
from guidami_ai_patente_ingestor.repositories import KnowledgeChunkStoreRepository


def _chunk(number: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        source="cds",
        article_number=number,
        article_title=f"Articolo {number}",
        comma_index=0,
        chunk_text=f"Testo {number}.",
        is_repealed=False,
        source_url=f"https://example.com/art-{number}",
    )


def test_required_keys() -> None:
    repo = MagicMock(spec=KnowledgeChunkStoreRepository)
    assert StoreChunksStep("store", "cds", repo).get_required_keys() == {
        context_keys.CHUNK_ENTITIES
    }


def test_produced_keys_is_empty_set() -> None:
    repo = MagicMock(spec=KnowledgeChunkStoreRepository)
    assert StoreChunksStep("store", "cds", repo).get_produced_keys() == set()


def test_execute_deletes_source_then_bulk_inserts() -> None:
    repo = MagicMock(spec=KnowledgeChunkStoreRepository)
    chunks = [_chunk("1"), _chunk("2")]
    context = FlowContext({context_keys.CHUNK_ENTITIES: chunks})

    StoreChunksStep("store", "cap", repo).execute(context)

    # delete-by-source BEFORE the insert, with the injected source
    assert repo.mock_calls == [call.delete_source("cap"), call.bulk_insert(chunks)]
