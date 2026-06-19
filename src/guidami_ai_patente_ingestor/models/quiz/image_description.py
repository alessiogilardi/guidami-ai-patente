from pydantic import BaseModel, ConfigDict


class ImageDescription(BaseModel):
    """Descrizione di un segnale stradale prodotta dal vision LLM."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
