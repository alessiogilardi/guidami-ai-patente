import os
from unittest.mock import MagicMock

import litellm
import pytest

from commons.clients import LiteLLMEmbeddingClient, SentenceTransformerEmbeddingClient
from commons.configs import EmbeddingConfig


class _FakeEmbeddingResponse:
    """Imita la `EmbeddingResponse` di litellm: attributo `data` con dict per input."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self.data = [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ]


# ---------------------------------------------------------------------------
# EmbeddingConfig
# ---------------------------------------------------------------------------


def test_embedding_config_defaults_to_text_embedding_3_small() -> None:
    config = EmbeddingConfig()
    assert config.model_name == "openrouter/openai/text-embedding-3-small"
    assert config.vector_dim == 1536


# ---------------------------------------------------------------------------
# LiteLLMEmbeddingClient
# ---------------------------------------------------------------------------


@pytest.fixture
def cloud_config() -> EmbeddingConfig:
    return EmbeddingConfig(model_name="openrouter/openai/text-embedding-3-small", vector_dim=1536)


def test_embed_query_returns_single_vector_of_configured_dimension(
    monkeypatch: pytest.MonkeyPatch, cloud_config: EmbeddingConfig
) -> None:
    captured: dict[str, object] = {}

    def fake_embedding(**kwargs: object) -> _FakeEmbeddingResponse:
        captured.update(kwargs)
        return _FakeEmbeddingResponse([[0.1] * cloud_config.vector_dim])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)

    vector = LiteLLMEmbeddingClient(cloud_config).embed_query(
        "Quando si accendono gli abbaglianti?"
    )

    assert len(vector) == cloud_config.vector_dim
    assert captured["model"] == cloud_config.model_name
    assert captured["input"] == ["Quando si accendono gli abbaglianti?"]


def test_embed_passages_returns_one_vector_per_input(
    monkeypatch: pytest.MonkeyPatch, cloud_config: EmbeddingConfig
) -> None:
    def fake_embedding(**kwargs: object) -> _FakeEmbeddingResponse:
        texts = kwargs["input"]
        assert isinstance(texts, list)
        return _FakeEmbeddingResponse([[0.0] * cloud_config.vector_dim for _ in texts])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)

    vectors = LiteLLMEmbeddingClient(cloud_config).embed_passages(["Articolo 1", "Articolo 2"])

    assert len(vectors) == 2
    assert all(len(vector) == cloud_config.vector_dim for vector in vectors)


def test_embed_passages_preserves_input_order_even_if_response_is_unordered(
    monkeypatch: pytest.MonkeyPatch, cloud_config: EmbeddingConfig
) -> None:
    def fake_embedding(**kwargs: object) -> _FakeEmbeddingResponse:
        response = _FakeEmbeddingResponse([[1.0], [2.0]])
        response.data = list(reversed(response.data))  # provider restituisce fuori ordine
        return response

    monkeypatch.setattr(litellm, "embedding", fake_embedding)

    vectors = LiteLLMEmbeddingClient(cloud_config).embed_passages(["a", "b"])

    assert vectors == [[1.0], [2.0]]


def test_no_prefix_is_added_to_litellm_inputs(
    monkeypatch: pytest.MonkeyPatch, cloud_config: EmbeddingConfig
) -> None:
    def fake_embedding(**kwargs: object) -> _FakeEmbeddingResponse:
        assert kwargs["input"] == ["testo grezzo"]
        return _FakeEmbeddingResponse([[0.0] * cloud_config.vector_dim])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)

    LiteLLMEmbeddingClient(cloud_config).embed_passages(["testo grezzo"])


def test_dimensions_is_forwarded_only_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_embedding(**kwargs: object) -> _FakeEmbeddingResponse:
        captured.clear()
        captured.update(kwargs)
        return _FakeEmbeddingResponse([[0.0] * 8])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)

    config_no_dim = EmbeddingConfig(
        model_name="openrouter/openai/text-embedding-3-small", vector_dim=1536, dimensions=None
    )
    LiteLLMEmbeddingClient(config_no_dim).embed_query("x")
    assert "dimensions" not in captured

    config_with_dim = EmbeddingConfig(
        model_name="openrouter/openai/text-embedding-3-small", vector_dim=1536, dimensions=1024
    )
    LiteLLMEmbeddingClient(config_with_dim).embed_query("x")
    assert captured["dimensions"] == 1024


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="richiede OPENROUTER_API_KEY per chiamare l'endpoint OpenRouter reale",
)
def test_embed_query_against_openrouter_returns_configured_dimension() -> None:
    config = EmbeddingConfig(
        model_name="openrouter/openai/text-embedding-3-small", vector_dim=1536
    )
    vector = LiteLLMEmbeddingClient(config).embed_query("Quando si accendono gli abbaglianti?")

    assert len(vector) == config.vector_dim


# ---------------------------------------------------------------------------
# SentenceTransformerEmbeddingClient — test offline con SentenceTransformer mockato
# ---------------------------------------------------------------------------


def _mock_sentence_transformer_class(
    monkeypatch: pytest.MonkeyPatch, mock_model: MagicMock
) -> None:
    """Sostituisce SentenceTransformer nel package sentence_transformers con un fake.

    Import locale: il client la importa dentro __init__ per evitare il costo
    dell'import di sentence-transformers/torch nelle sessioni che non la usano.
    """
    import sentence_transformers

    fake_class = MagicMock(return_value=mock_model)
    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", fake_class)


def test_st_embed_query_adds_no_prefix_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    captured: list[str] = []
    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda text, normalize_embeddings=False: (
        captured.append(text) or np.array([0.1] * 1024)
    )
    _mock_sentence_transformer_class(monkeypatch, mock_model)

    client = SentenceTransformerEmbeddingClient(EmbeddingConfig())
    client.embed_query("Quando si accendono gli abbaglianti?")

    assert captured == ["Quando si accendono gli abbaglianti?"]


def test_st_embed_passages_adds_no_prefix_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    captured: list[list[str]] = []
    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda texts, normalize_embeddings=False: (
        captured.append(texts) or np.array([[0.1] * 1024] * len(texts))
    )
    _mock_sentence_transformer_class(monkeypatch, mock_model)

    client = SentenceTransformerEmbeddingClient(EmbeddingConfig())
    client.embed_passages(["Articolo 1", "Articolo 2"])

    assert captured == [["Articolo 1", "Articolo 2"]]


def test_st_encode_called_with_normalize_embeddings_true(monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    encode_kwargs: dict[str, object] = {}
    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda text, normalize_embeddings=False: (
        encode_kwargs.update({"normalize_embeddings": normalize_embeddings})
        or np.array([0.1] * 1024)
    )
    _mock_sentence_transformer_class(monkeypatch, mock_model)

    SentenceTransformerEmbeddingClient(EmbeddingConfig()).embed_query("test")

    assert encode_kwargs["normalize_embeddings"] is True


def test_st_custom_query_prefix_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    captured: list[str] = []
    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda text, normalize_embeddings=False: (
        captured.append(text) or np.array([0.1] * 384)
    )
    _mock_sentence_transformer_class(monkeypatch, mock_model)

    config = EmbeddingConfig(model_name="intfloat/multilingual-e5-small", vector_dim=384)
    client = SentenceTransformerEmbeddingClient(
        config, query_prefix="query: ", passage_prefix="passage: "
    )
    client.embed_query("test")

    assert captured == ["query: test"]


def test_st_custom_passage_prefix_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    captured: list[list[str]] = []
    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda texts, normalize_embeddings=False: (
        captured.append(texts) or np.array([[0.1] * 384] * len(texts))
    )
    _mock_sentence_transformer_class(monkeypatch, mock_model)

    config = EmbeddingConfig(model_name="intfloat/multilingual-e5-small", vector_dim=384)
    client = SentenceTransformerEmbeddingClient(
        config, query_prefix="query: ", passage_prefix="passage: "
    )
    client.embed_passages(["Articolo 1"])

    assert captured == [["passage: Articolo 1"]]


@pytest.mark.integration
def test_st_bge_m3_embed_query_returns_1024_dim_vector() -> None:
    config = EmbeddingConfig()
    client = SentenceTransformerEmbeddingClient(config)
    vector = client.embed_query("Quando si accendono gli abbaglianti?")

    assert len(vector) == 1024
