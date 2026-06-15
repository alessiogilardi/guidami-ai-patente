from commons.entities.knowledge import KnowledgeChunk


def test_knowledge_chunk_defaults_embedding_to_none() -> None:
    chunk = KnowledgeChunk(
        source="cds",
        article_number="94-bis",
        article_title="Esempio",
        comma_index=1,
        chunk_text="Testo del comma",
        is_repealed=False,
        source_url="https://example.com/art-94-bis",
    )

    assert chunk.embedding is None
