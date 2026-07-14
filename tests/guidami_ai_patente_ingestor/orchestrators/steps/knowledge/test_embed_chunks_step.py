"""Tests for EmbedChunksStep."""

from flowstep import FlowContext

from commons.ai.embedding import EmbeddingClient, EmbeddingService
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableChunkModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import EmbedChunksStep


class _FakeClient(EmbeddingClient):
    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] for t in texts]


def _make_service(batch_size: int = 10) -> EmbeddingService:
    return EmbeddingService(batch_size=batch_size, client=_FakeClient())


def _make_chunk(number: str, repealed: bool = False) -> EmbeddableChunkModel:
    return EmbeddableChunkModel(
        source="cds",
        article_number=number,
        article_title=f"Articolo {number}",
        comma_index=0,
        chunk_text=f"Testo {number}.",
        is_repealed=repealed,
        source_url=f"https://example.com/art-{number}",
    )


def test_required_keys() -> None:
    step = EmbedChunksStep("embed", embed_repealed=False, embedding_service=_make_service())
    assert step.get_required_keys() == {context_keys.EMBEDDABLE_CHUNKS}


def test_produced_keys() -> None:
    step = EmbedChunksStep("embed", embed_repealed=False, embedding_service=_make_service())
    assert step.get_produced_keys() == {context_keys.EMBEDDABLE_CHUNKS}


def test_embed_repealed_false_skips_repealed_but_keeps_them_in_context() -> None:
    """Baseline behavior: repealed stored with embedding=None, non-repealed with a vector."""
    normal = _make_chunk("1", repealed=False)
    repealed = _make_chunk("2", repealed=True)
    chunks = [normal, repealed]

    context = FlowContext({context_keys.EMBEDDABLE_CHUNKS: chunks})
    step = EmbedChunksStep("embed", embed_repealed=False, embedding_service=_make_service())
    step.execute(context)

    result: list[EmbeddableChunkModel] = context.get(context_keys.EMBEDDABLE_CHUNKS)
    assert len(result) == 2, "both chunks must be present in the context"

    # the non-repealed one has the vector
    assert result[0].embedding is not None
    # the repealed one has embedding=None
    assert result[1].embedding is None


def test_embed_repealed_true_embeds_all_chunks() -> None:
    normal = _make_chunk("1", repealed=False)
    repealed = _make_chunk("2", repealed=True)
    chunks = [normal, repealed]

    context = FlowContext({context_keys.EMBEDDABLE_CHUNKS: chunks})
    step = EmbedChunksStep("embed", embed_repealed=True, embedding_service=_make_service())
    step.execute(context)

    result: list[EmbeddableChunkModel] = context.get(context_keys.EMBEDDABLE_CHUNKS)
    assert all(c.embedding is not None for c in result), "all chunks must be embedded"


def test_execute_mutates_in_place_and_writes_full_list_to_context() -> None:
    """The original list is mutated in place and re-written to CHUNKS."""
    normal1 = _make_chunk("1", repealed=False)
    normal2 = _make_chunk("2", repealed=False)
    chunks = [normal1, normal2]

    context = FlowContext({context_keys.EMBEDDABLE_CHUNKS: chunks})
    step = EmbedChunksStep("embed", embed_repealed=False, embedding_service=_make_service())
    step.execute(context)

    result: list[EmbeddableChunkModel] = context.get(context_keys.EMBEDDABLE_CHUNKS)
    assert result is chunks  # same list (mutated in place and re-written)
    assert all(c.embedding is not None for c in result)


def test_execute_assigns_correct_vector_values() -> None:
    """The vector must match embedded_text (via FakeClient)."""
    chunk = _make_chunk("1", repealed=False)
    expected_vector = [float(len(chunk.embedded_text))]

    context = FlowContext({context_keys.EMBEDDABLE_CHUNKS: [chunk]})
    step = EmbedChunksStep("embed", embed_repealed=False, embedding_service=_make_service())
    step.execute(context)

    result: list[EmbeddableChunkModel] = context.get(context_keys.EMBEDDABLE_CHUNKS)
    assert result[0].embedding == expected_vector


def test_execute_with_empty_chunks_list_is_noop() -> None:
    context = FlowContext({context_keys.EMBEDDABLE_CHUNKS: []})
    step = EmbedChunksStep("embed", embed_repealed=False, embedding_service=_make_service())
    step.execute(context)

    result: list[EmbeddableChunkModel] = context.get(context_keys.EMBEDDABLE_CHUNKS)
    assert result == []
