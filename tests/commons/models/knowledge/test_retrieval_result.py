from commons.entities.knowledge import KnowledgeChunk
from commons.models.knowledge import RetrievalResult


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
