from pydantic import BaseModel, ConfigDict


class SimplifiedDefinition(BaseModel):
    """One Italian term paired with its plain-language rendering, ready to persist."""

    model_config = ConfigDict(frozen=True)

    term: str
    definition_plain: str
