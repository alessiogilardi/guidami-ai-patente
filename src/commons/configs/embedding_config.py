from pydantic import BaseModel, ConfigDict


class EmbeddingConfig(BaseModel):
    """Configurazione del modello di embedding condivisa tra ingestor e app."""

    model_config = ConfigDict(frozen=True)

    model_name: str = "intfloat/multilingual-e5-small"
    vector_dim: int = 384
    query_prefix: str = "query: "
    passage_prefix: str = "passage: "
