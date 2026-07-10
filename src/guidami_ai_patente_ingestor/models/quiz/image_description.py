from pydantic import BaseModel, ConfigDict


class ImageDescription(BaseModel):
    """Description of a road sign produced by the vision LLM."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
