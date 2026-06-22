"""Test per EmbedChunksStep."""

from commons.clients import EmbeddingClient
from commons.entities.knowledge import KnowledgeChunk
from commons.flowstep import FlowContext
from commons.services.embeddings import EmbeddingService
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import EmbedChunksStep


class _FakeClient(EmbeddingClient):
    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] for t in texts]


def _make_service(batch_size: int = 10) -> EmbeddingService:
    return EmbeddingService(_FakeClient(), batch_size=batch_size)


def _make_chunk(number: str, repealed: bool = False) -> KnowledgeChunk:
    return KnowledgeChunk(
        source="cds",
        article_number=number,
        article_title=f"Articolo {number}",
        comma_index=0,
        chunk_text=f"Testo {number}.",
        is_repealed=repealed,
        source_url=f"https://example.com/art-{number}",
    )


def test_required_keys() -> None:
    step = EmbedChunksStep("embed", _make_service(), embed_repealed=False)
    assert step.get_required_keys() == {context_keys.CHUNKS}


def test_produced_keys() -> None:
    step = EmbedChunksStep("embed", _make_service(), embed_repealed=False)
    assert step.get_produced_keys() == {context_keys.CHUNKS}


def test_embed_repealed_false_skips_repealed_but_keeps_them_in_context() -> None:
    """Comportamento baseline: repealed storati con embedding=None, non-repealed con vettore."""
    normal = _make_chunk("1", repealed=False)
    repealed = _make_chunk("2", repealed=True)
    chunks = [normal, repealed]

    context = FlowContext({context_keys.CHUNKS: chunks})
    step = EmbedChunksStep("embed", _make_service(), embed_repealed=False)
    step.execute(context)

    result: list[KnowledgeChunk] = context.get(context_keys.CHUNKS)
    assert len(result) == 2, "entrambi i chunk devono essere presenti nel context"

    # il non-repealed ha il vettore
    assert result[0].embedding is not None
    # il repealed ha embedding=None
    assert result[1].embedding is None


def test_embed_repealed_true_embeds_all_chunks() -> None:
    normal = _make_chunk("1", repealed=False)
    repealed = _make_chunk("2", repealed=True)
    chunks = [normal, repealed]

    context = FlowContext({context_keys.CHUNKS: chunks})
    step = EmbedChunksStep("embed", _make_service(), embed_repealed=True)
    step.execute(context)

    result: list[KnowledgeChunk] = context.get(context_keys.CHUNKS)
    assert all(c.embedding is not None for c in result), "tutti i chunk devono essere embeddati"


def test_execute_mutates_in_place_and_writes_full_list_to_context() -> None:
    """La lista originale è mutata in place e ri-scritta in CHUNKS."""
    normal1 = _make_chunk("1", repealed=False)
    normal2 = _make_chunk("2", repealed=False)
    chunks = [normal1, normal2]

    context = FlowContext({context_keys.CHUNKS: chunks})
    step = EmbedChunksStep("embed", _make_service(), embed_repealed=False)
    step.execute(context)

    result: list[KnowledgeChunk] = context.get(context_keys.CHUNKS)
    assert result is chunks  # stessa lista (mutata in place e ri-scritta)
    assert all(c.embedding is not None for c in result)


def test_execute_assigns_correct_vector_values() -> None:
    """Il vettore deve corrispondere all'embedded_text (tramite FakeClient)."""
    chunk = _make_chunk("1", repealed=False)
    expected_vector = [float(len(chunk.embedded_text))]

    context = FlowContext({context_keys.CHUNKS: [chunk]})
    step = EmbedChunksStep("embed", _make_service(), embed_repealed=False)
    step.execute(context)

    result: list[KnowledgeChunk] = context.get(context_keys.CHUNKS)
    assert result[0].embedding == expected_vector


def test_execute_with_empty_chunks_list_is_noop() -> None:
    context = FlowContext({context_keys.CHUNKS: []})
    step = EmbedChunksStep("embed", _make_service(), embed_repealed=False)
    step.execute(context)

    result: list[KnowledgeChunk] = context.get(context_keys.CHUNKS)
    assert result == []
