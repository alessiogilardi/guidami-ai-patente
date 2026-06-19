import pytest

from commons.clients import EmbeddingClient
from commons.entities.knowledge import KnowledgeChunk
from commons.services.embeddings import Embeddable, Embedded, EmbeddingService
from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizQuestion


class _RecordingFakeClient(EmbeddingClient):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(t))] for t in texts]


class _FakeEmbeddable:
    def __init__(self, text: str) -> None:
        self._text = text
        self.embedding: list[float] | None = None

    @property
    def embedded_text(self) -> str:
        return self._text


def _accepts_embeddable(x: Embeddable) -> str:
    return x.embedded_text


class TestEmbeddingService:
    def _make_service(self, batch_size: int = 10) -> EmbeddingService:
        return EmbeddingService(_RecordingFakeClient(), batch_size)

    def test_length_and_order(self) -> None:
        items = [_FakeEmbeddable("ab"), _FakeEmbeddable("cde"), _FakeEmbeddable("f")]
        result = self._make_service().embed(items)
        assert len(result) == 3
        assert result == [[2.0], [3.0], [1.0]]

    def test_batching(self) -> None:
        items = [_FakeEmbeddable(f"item{i}") for i in range(5)]
        client = _RecordingFakeClient()
        service = EmbeddingService(client, batch_size=2)
        service.embed(items)
        assert len(client.calls) == 3
        assert client.calls[0] == ["item0", "item1"]
        assert client.calls[1] == ["item2", "item3"]
        assert client.calls[2] == ["item4"]

    def test_empty_input(self) -> None:
        client = _RecordingFakeClient()
        result = EmbeddingService(client, batch_size=10).embed([])
        assert result == []
        assert client.calls == []

    def test_invalid_batch_size_zero(self) -> None:
        with pytest.raises(ValueError):
            EmbeddingService(_RecordingFakeClient(), 0)

    def test_invalid_batch_size_negative(self) -> None:
        with pytest.raises(ValueError):
            EmbeddingService(_RecordingFakeClient(), -1)

    def test_purity(self) -> None:
        item = _FakeEmbeddable("hello")
        self._make_service().embed([item])
        assert item.embedding is None

    def test_protocol_conformance_knowledge_chunk(self) -> None:
        chunk = KnowledgeChunk(
            source="cds",
            article_number="1",
            article_title="Titolo",
            comma_index=0,
            chunk_text="testo",
            is_repealed=False,
            source_url="http://example.com",
        )
        assert isinstance(chunk, Embeddable)
        assert isinstance(chunk, Embedded)
        assert _accepts_embeddable(chunk) == chunk.embedded_text

    def test_protocol_conformance_embeddable_quiz_question(self) -> None:
        question = EmbeddableQuizQuestion(
            number="1",
            question_id=1,
            topic="topico",
            text="domanda",
            correct_answer=True,
        )
        assert isinstance(question, Embeddable)
        assert isinstance(question, Embedded)
        assert _accepts_embeddable(question) == question.embedded_text
