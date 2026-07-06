from pydantic import BaseModel, ConfigDict, SecretStr


class PostgresConnectionConfig(BaseModel):
    """Configurazione di connessione Postgres condivisa tra ingestor e applicativo."""

    model_config = ConfigDict(frozen=True)

    host: str
    port: int = 5432
    user: str
    password: SecretStr
    dbname: str
    sslmode: str | None = None
    connect_timeout: int = 5
