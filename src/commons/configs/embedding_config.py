from pydantic import BaseModel, ConfigDict


class EmbeddingConfig(BaseModel):
    """Configurazione dell'embedder cloud (OpenRouter via litellm)."""

    model_config = ConfigDict(frozen=True)

    model_name: str = "openrouter/openai/text-embedding-3-small"
    vector_dim: int = 1536
    # Matryoshka: se valorizzato, accorcia l'output del modello; deve combaciare
    # con vector_dim e con la dimensione della colonna VECTOR(N). Default: full.
    dimensions: int | None = None
    timeout: float = 30.0
    num_retries: int = 3
