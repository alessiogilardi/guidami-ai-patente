from pydantic import BaseModel, ConfigDict


class SourceConfig(BaseModel):
    """Posizione di una source (directory + file) all'interno di un layer."""

    model_config = ConfigDict(frozen=True)

    dir: str
    file: str
