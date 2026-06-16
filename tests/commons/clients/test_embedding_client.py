import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

import litellm
import pytest

from commons.clients import E5SmallEmbeddingClient, LiteLLMEmbeddingClient
from commons.configs import EmbeddingConfig


class _FakeEmbeddingResponse:
    """Imita la `EmbeddingResponse` di litellm: attributo `data` con dict per input."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self.data = [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ]


@pytest.fixture
def config() -> EmbeddingConfig:
    return EmbeddingConfig()


def test_embed_query_returns_single_vector_of_configured_dimension(
    monkeypatch: pytest.MonkeyPatch, config: EmbeddingConfig
) -> None:
    captured: dict[str, object] = {}

    def fake_embedding(**kwargs: object) -> _FakeEmbeddingResponse:
        captured.update(kwargs)
        return _FakeEmbeddingResponse([[0.1] * config.vector_dim])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)

    vector = LiteLLMEmbeddingClient(config).embed_query("Quando si accendono gli abbaglianti?")

    assert len(vector) == config.vector_dim
    assert captured["model"] == config.model_name
    assert captured["input"] == ["Quando si accendono gli abbaglianti?"]


def test_embed_passages_returns_one_vector_per_input(
    monkeypatch: pytest.MonkeyPatch, config: EmbeddingConfig
) -> None:
    def fake_embedding(**kwargs: object) -> _FakeEmbeddingResponse:
        texts = kwargs["input"]
        assert isinstance(texts, list)
        return _FakeEmbeddingResponse([[0.0] * config.vector_dim for _ in texts])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)

    vectors = LiteLLMEmbeddingClient(config).embed_passages(["Articolo 1", "Articolo 2"])

    assert len(vectors) == 2
    assert all(len(vector) == config.vector_dim for vector in vectors)


def test_embed_passages_preserves_input_order_even_if_response_is_unordered(
    monkeypatch: pytest.MonkeyPatch, config: EmbeddingConfig
) -> None:
    def fake_embedding(**kwargs: object) -> _FakeEmbeddingResponse:
        response = _FakeEmbeddingResponse([[1.0], [2.0]])
        response.data = list(reversed(response.data))  # provider restituisce fuori ordine
        return response

    monkeypatch.setattr(litellm, "embedding", fake_embedding)

    vectors = LiteLLMEmbeddingClient(config).embed_passages(["a", "b"])

    assert vectors == [[1.0], [2.0]]


def test_no_e5_prefix_is_added_to_inputs(
    monkeypatch: pytest.MonkeyPatch, config: EmbeddingConfig
) -> None:
    def fake_embedding(**kwargs: object) -> _FakeEmbeddingResponse:
        assert kwargs["input"] == ["testo grezzo"]  # niente 'passage: '/'query: '
        return _FakeEmbeddingResponse([[0.0] * config.vector_dim])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)

    LiteLLMEmbeddingClient(config).embed_passages(["testo grezzo"])


def test_dimensions_is_forwarded_only_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_embedding(**kwargs: object) -> _FakeEmbeddingResponse:
        captured.clear()
        captured.update(kwargs)
        return _FakeEmbeddingResponse([[0.0] * 8])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)

    LiteLLMEmbeddingClient(EmbeddingConfig(dimensions=None)).embed_query("x")
    assert "dimensions" not in captured

    LiteLLMEmbeddingClient(EmbeddingConfig(dimensions=1024)).embed_query("x")
    assert captured["dimensions"] == 1024


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="richiede OPENROUTER_API_KEY per chiamare l'endpoint OpenRouter reale",
)
def test_embed_query_against_openrouter_returns_configured_dimension() -> None:
    config = EmbeddingConfig()
    vector = LiteLLMEmbeddingClient(config).embed_query("Quando si accendono gli abbaglianti?")

    assert len(vector) == config.vector_dim


# ---------------------------------------------------------------------------
# E5SmallEmbeddingClient — test offline con SentenceTransformer mockato
# ---------------------------------------------------------------------------

def _mock_sentence_transformers(monkeypatch: pytest.MonkeyPatch, mock_model: MagicMock) -> None:
    """Inietta un modulo `sentence_transformers` fittizio nel sys.modules."""
    mock_st = ModuleType("sentence_transformers")
    mock_st.SentenceTransformer = MagicMock(return_value=mock_model)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", mock_st)


def test_e5_embed_query_applies_query_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    captured: list[str] = []
    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda text, normalize_embeddings=False: (
        captured.append(text) or np.array([0.1] * 384)
    )

    _mock_sentence_transformers(monkeypatch, mock_model)

    config = EmbeddingConfig(model_name="intfloat/multilingual-e5-small", vector_dim=384)
    client = E5SmallEmbeddingClient(config)
    client.embed_query("Quando si accendono gli abbaglianti?")

    assert captured == ["query: Quando si accendono gli abbaglianti?"]


def test_e5_embed_passages_applies_passage_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    captured: list[list[str]] = []
    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda texts, normalize_embeddings=False: (
        captured.append(texts) or np.array([[0.1] * 384] * len(texts))
    )
    _mock_sentence_transformers(monkeypatch, mock_model)

    config = EmbeddingConfig(model_name="intfloat/multilingual-e5-small", vector_dim=384)
    client = E5SmallEmbeddingClient(config)
    client.embed_passages(["Articolo 1", "Articolo 2"])

    assert captured == [["passage: Articolo 1", "passage: Articolo 2"]]


def test_e5_custom_prefixes_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    captured: list[str] = []
    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda text, normalize_embeddings=False: (
        captured.append(text) or np.array([0.1] * 384)
    )
    _mock_sentence_transformers(monkeypatch, mock_model)

    config = EmbeddingConfig(model_name="intfloat/multilingual-e5-small", vector_dim=384)
    client = E5SmallEmbeddingClient(config, query_prefix="Q: ", passage_prefix="P: ")
    client.embed_query("test")

    assert captured == ["Q: test"]


def test_e5_raises_import_error_when_sentence_transformers_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # type: ignore[arg-type]

    config = EmbeddingConfig(model_name="intfloat/multilingual-e5-small", vector_dim=384)
    with pytest.raises(ImportError, match="sentence-transformers"):
        E5SmallEmbeddingClient(config)
