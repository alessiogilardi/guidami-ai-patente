from pydantic import BaseModel, ConfigDict


class TranslatedTerm(BaseModel):
    model_config = ConfigDict(frozen=True)

    term: str
    term_ru: str
