from pydantic import BaseModel, ConfigDict


class GlossaryTermRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    term: str
    definition: str
