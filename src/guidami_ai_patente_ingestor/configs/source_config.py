from pydantic import BaseModel, ConfigDict


class SourceConfig(BaseModel):
    """Location of a source (directory + file) within a layer."""

    model_config = ConfigDict(frozen=True)

    dir: str
    file: str
