from pydantic import BaseModel, ConfigDict


class EmbeddingConfig(BaseModel):
    """Configurazione dell'embedder di default locale (BAAI/bge-m3, 1024 dim).

    I campi cloud (`dimensions`, `timeout`, `num_retries`) sono ignorati dal client
    locale e restano per l'alternativa `LiteLLMEmbeddingClient` (A/B di qualità).
    """

    model_config = ConfigDict(frozen=True)

    model_name: str = "BAAI/bge-m3"
    vector_dim: int = 1024
    # Matryoshka: se valorizzato, accorcia l'output del modello; deve combaciare
    # con vector_dim e con la dimensione della colonna VECTOR(N). Default: full.
    dimensions: int | None = None
    timeout: float = 30.0
    num_retries: int = 3
