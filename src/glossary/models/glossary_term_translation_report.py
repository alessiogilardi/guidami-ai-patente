from pydantic import BaseModel, ConfigDict


class GlossaryTermTranslationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    translated: int
    still_missing: int
