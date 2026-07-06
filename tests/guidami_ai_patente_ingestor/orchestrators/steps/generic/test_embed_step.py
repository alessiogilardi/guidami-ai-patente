"""Test per EmbedStep (step generico di embedding)."""

from collections.abc import Sequence

import pytest

from commons.clients import EmbeddingClient
from commons.services.embeddings import EmbeddingService
from flowstep import FlowContext
from guidami_ai_patente_ingestor.orchestrators.steps.generic import EmbedStep


class _FakeClient(EmbeddingClient):
    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] for t in texts]


class _FakeEmbeddable:
    """Soddisfa il Protocol Embedded strutturalmente."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.embedding: list[float] | None = None

    @property
    def embedded_text(self) -> str:
        return self._text


def _make_service(batch_size: int = 10) -> EmbeddingService:
    return EmbeddingService(batch_size=batch_size, client=_FakeClient())


def test_required_and_produced_keys_equal_items_key() -> None:
    step = EmbedStep("embed", items_key="my_items", embedding_service=_make_service())
    assert step.get_required_keys() == {"my_items"}
    assert step.get_produced_keys() == {"my_items"}


def test_execute_assigns_embedding_and_writes_back_to_context() -> None:
    items = [
        _FakeEmbeddable("hello"),
        _FakeEmbeddable("world!"),
    ]
    context = FlowContext({"my_items": items})
    step = EmbedStep("embed", items_key="my_items", embedding_service=_make_service())

    step.execute(context)

    # ogni item deve avere l'embedding valorizzato
    assert items[0].embedding == [float(len("hello"))]
    assert items[1].embedding == [float(len("world!"))]

    # context.get deve ritornare gli item aggiornati
    result = context.get("my_items")
    assert result is items  # stessa lista (mutata in place e ri-scritta)


def test_execute_raises_value_error_on_length_mismatch() -> None:
    """Se EmbeddingService ritorna meno vettori degli item, zip(strict=True) alza ValueError."""

    class _ShortEmbeddingService(EmbeddingService):
        def execute(self, input: Sequence) -> list[list[float]]:  # type: ignore[override]
            # Restituisce un vettore in meno degli item
            return [[1.0]] * (len(input) - 1)

    short_service = _ShortEmbeddingService(batch_size=10, client=_FakeClient())
    items = [_FakeEmbeddable("a"), _FakeEmbeddable("b"), _FakeEmbeddable("c")]
    context = FlowContext({"items": items})
    step = EmbedStep("embed", items_key="items", embedding_service=short_service)

    with pytest.raises(ValueError):
        step.execute(context)
