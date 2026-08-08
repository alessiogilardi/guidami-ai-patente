from dataclasses import dataclass

from commons.ai.embedding.clients import EmbeddingClient
from commons.ai.embedding.services import EmbeddingService, ModelEmbeddingService


@dataclass
class _Article:
    title: str
    body: str


class _UppercaseComposer:
    def compose(self, model: _Article) -> str:
        return f"{model.title} {model.body}".upper()


class _RecordingFakeClient(EmbeddingClient):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(t))] for t in texts]


def _make_service(
    batch_size: int = 10,
) -> tuple[ModelEmbeddingService, _RecordingFakeClient]:
    client = _RecordingFakeClient()
    embedding_service = EmbeddingService(batch_size, client)
    return ModelEmbeddingService(_UppercaseComposer(), embedding_service), client


def test_execute_aligns_model_text_and_vector_in_order() -> None:
    service, client = _make_service()
    articles = [_Article(title="Art. 1", body="Uno"), _Article(title="Art. 2", body="Due")]

    results = service.execute(articles)

    assert [r.model for r in results] == articles
    assert results[0].text == "ART. 1 UNO"
    assert results[1].text == "ART. 2 DUE"
    assert results[0].embedding == [float(len("ART. 1 UNO"))]
    assert client.calls == [["ART. 1 UNO", "ART. 2 DUE"]]


def test_execute_delegates_batching_to_the_injected_embedding_service() -> None:
    service, client = _make_service(batch_size=1)
    articles = [_Article(title="A", body="1"), _Article(title="B", body="2")]

    service.execute(articles)

    assert len(client.calls) == 2


def test_execute_returns_empty_list_for_empty_input() -> None:
    service, client = _make_service()

    results = service.execute([])

    assert results == []
    assert client.calls == []


def test_service_is_invocable_via_call() -> None:
    service, _ = _make_service()
    articles = [_Article(title="Art. 1", body="Uno")]

    results = service(articles)

    assert len(results) == 1
