from pydantic import BaseModel, ConfigDict


class VectorStoreConfig(BaseModel):
    """Configurazione di accesso al vector store condivisa tra ingestor e app."""

    model_config = ConfigDict(frozen=True)

    database_url: str
    table_name: str = "knowledge_chunks"
