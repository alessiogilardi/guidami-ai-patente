from pydantic import BaseModel, ConfigDict, Field, SecretStr


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
    pool_min_size: int = Field(
        default=1,
        ge=1,
        description="Connections opened eagerly by PostgresClient's pool (AD-26).",
    )
    pool_max_size: int = Field(
        default=8,
        ge=1,
        description=(
            "Upper bound on pooled connections. Deployment capacity, never judge "
            "identity: it must not reach LabelingConfig (spec 0012, AD-26)."
        ),
    )
