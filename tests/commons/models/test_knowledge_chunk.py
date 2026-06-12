from commons.models.knowledge import KnowledgeChunk, RetrievalResult


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


def test_retrieval_result_wraps_chunk_with_score() -> None:
    chunk = KnowledgeChunk(
        source="cap",
        article_number="118",
        article_title="Esempio CAP",
        comma_index=1,
        chunk_text="Testo del comma",
        is_repealed=True,
        source_url="https://example.com/art-118",
        embedding=[0.1, 0.2],
    )

    result = RetrievalResult(chunk=chunk, score=0.87)

    assert result.chunk.article_number == "118"
    assert result.score == 0.87
