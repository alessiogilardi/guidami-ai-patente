import pytest

from commons.clients import E5SmallEmbeddingClient
from commons.configs import EmbeddingConfig


@pytest.fixture(scope="module")
def client() -> E5SmallEmbeddingClient:
    return E5SmallEmbeddingClient(EmbeddingConfig())


@pytest.mark.integration
def test_embed_query_returns_configured_dimension(client: E5SmallEmbeddingClient) -> None:
    vector = client.embed_query("Quando si accendono gli abbaglianti?")

    assert len(vector) == EmbeddingConfig().vector_dim


@pytest.mark.integration
def test_embed_passages_returns_one_vector_per_input(client: E5SmallEmbeddingClient) -> None:
    vectors = client.embed_passages(["Articolo 1", "Articolo 2"])

    assert len(vectors) == 2
    assert all(len(vector) == EmbeddingConfig().vector_dim for vector in vectors)
