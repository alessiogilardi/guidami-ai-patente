from pydantic import BaseModel, ConfigDict, SecretStr


class PostgresConnectionConfig(BaseModel):
    """Postgres connection configuration shared between ingestor and application."""

    model_config = ConfigDict(frozen=True)

    host: str
    port: int = 5432
    user: str
    password: SecretStr
    dbname: str
    sslmode: str | None = None
    connect_timeout: int = 5
