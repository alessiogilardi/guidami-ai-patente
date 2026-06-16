from pydantic import BaseModel, ConfigDict


class EmbeddingConfig(BaseModel):
    """Configurazione dell'embedder di default cloud (text-embedding-3-small, 1536 dim).

    Usato da `LiteLLMEmbeddingClient` via OpenRouter (`OPENROUTER_API_KEY`).
    I campi `timeout` e `num_retries` sono ignorati dal client locale
    `SentenceTransformerEmbeddingClient`.
    """

    model_config = ConfigDict(frozen=True)

    model_name: str = "openrouter/openai/text-embedding-3-small"
    vector_dim: int = 1536
    # Matryoshka: se valorizzato, accorcia l'output del modello; deve combaciare
    # con vector_dim e con la dimensione della colonna VECTOR(N). Default: full.
    dimensions: int | None = None
    timeout: float = 30.0
    num_retries: int = 3
