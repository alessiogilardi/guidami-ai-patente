from pydantic import BaseModel, ConfigDict, SecretStr


class VectorStoreConfig(BaseModel):
    """Configurazione di accesso al vector store condivisa tra ingestor e app."""

    model_config = ConfigDict(frozen=True)

    host: str
    port: int = 5432
    user: str
    password: SecretStr
    dbname: str
    sslmode: str | None = None
    table_name: str = "knowledge_chunks"
