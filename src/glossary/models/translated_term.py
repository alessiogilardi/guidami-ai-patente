from pydantic import BaseModel, ConfigDict


class TranslatedTerm(BaseModel):
    """One Italian term paired with its Russian rendering, ready to persist."""

    model_config = ConfigDict(frozen=True)

    term: str
    term_ru: str
