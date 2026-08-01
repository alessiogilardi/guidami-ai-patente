from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from commons.ai.embedding import Embeddable, Embedded, EmbeddingClient, EmbeddingService
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableArticleComma

if TYPE_CHECKING:
    # `tests` has no `__init__.py` (project convention) and is not importable as a
    # dotted package at runtime under `uv run pytest <file>` (console-script entry
    # point does not add the project root to sys.path). Type-only import, resolved
    # statically; never evaluated at runtime thanks to `from __future__ import
    # annotations`. Pytest matches fixtures by parameter name, not by annotation.
    from tests.conftest import RecordingProgressReporter


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
        return EmbeddingService(batch_size, _RecordingFakeClient())

    def test_length_and_order(self) -> None:
        items = [_FakeEmbeddable("ab"), _FakeEmbeddable("cde"), _FakeEmbeddable("f")]
        result = self._make_service().execute(items)
        assert len(result) == 3
        assert result == [[2.0], [3.0], [1.0]]

    def test_batching(self) -> None:
        items = [_FakeEmbeddable(f"item{i}") for i in range(5)]
        client = _RecordingFakeClient()
        service = EmbeddingService(batch_size=2, client=client)
        service.execute(items)
        assert len(client.calls) == 3
        assert client.calls[0] == ["item0", "item1"]
        assert client.calls[1] == ["item2", "item3"]
        assert client.calls[2] == ["item4"]

    def test_empty_input(self) -> None:
        client = _RecordingFakeClient()
        result = EmbeddingService(batch_size=10, client=client).execute([])
        assert result == []
        assert client.calls == []

    def test_invalid_batch_size_zero(self) -> None:
        with pytest.raises(ValueError):
            EmbeddingService(0, _RecordingFakeClient())

    def test_invalid_batch_size_negative(self) -> None:
        with pytest.raises(ValueError):
            EmbeddingService(-1, _RecordingFakeClient())

    def test_purity(self) -> None:
        item = _FakeEmbeddable("hello")
        self._make_service().execute([item])
        assert item.embedding is None

    def test_protocol_conformance_embeddable_article_comma(self) -> None:
        comma = EmbeddableArticleComma(
            source="cds",
            article_number="1",
            article_title="Titolo",
            comma_number="1",
            position=0,
            text="testo",
            is_repealed=False,
        )
        assert isinstance(comma, Embeddable)
        assert isinstance(comma, Embedded)
        assert _accepts_embeddable(comma) == comma.embedded_text

    def test_reports_one_tick_per_batch(
        self, progress_recorder: RecordingProgressReporter
    ) -> None:
        items = [_FakeEmbeddable(f"item{i}") for i in range(5)]
        client = _RecordingFakeClient()
        service = EmbeddingService(batch_size=2, client=client, progress=progress_recorder)

        service.execute(items)

        assert progress_recorder.calls[0] == ("begin_items", ("batches", 3))
        assert progress_recorder.count("advance_item") == 3
        assert progress_recorder.calls[-1] == ("end_items", ())

    def test_end_items_still_runs_when_a_batch_raises(
        self, progress_recorder: RecordingProgressReporter
    ) -> None:
        items = [_FakeEmbeddable(f"item{i}") for i in range(4)]
        client = _RecordingFakeClient()

        def _embed_passages(texts: list[str]) -> list[list[float]]:
            client.calls.append(list(texts))
            if len(client.calls) == 2:
                raise RuntimeError("embedding backend unavailable")
            return [[float(len(t))] for t in texts]

        client.embed_passages = _embed_passages  # type: ignore[method-assign]
        service = EmbeddingService(batch_size=2, client=client, progress=progress_recorder)

        with pytest.raises(RuntimeError):
            service.execute(items)

        assert progress_recorder.count("advance_item") == 1
        assert progress_recorder.calls[-1] == ("end_items", ())
