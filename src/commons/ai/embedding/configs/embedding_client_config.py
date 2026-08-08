from pydantic import BaseModel, ConfigDict


class EmbeddingClientConfig(BaseModel):
    """Configuration for the default cloud embedder (text-embedding-3-small, 1536 dim).

    Used by `LiteLLMEmbeddingClient` via OpenRouter (`OPENROUTER_API_KEY`).
    The `timeout` and `num_retries` fields are ignored by the local
    `SentenceTransformerEmbeddingClient` client.
    """

    model_config = ConfigDict(frozen=True)

    model_name: str = "openrouter/openai/text-embedding-3-small"
    vector_dim: int = 1536
    # Matryoshka: if set, truncates the model output; must match
    # vector_dim and the VECTOR(N) column size. Default: full.
    dimensions: int | None = None
    timeout: float = 30.0
    num_retries: int = 3
