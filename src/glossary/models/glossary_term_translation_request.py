from pydantic import BaseModel, ConfigDict


class GlossaryTermTranslationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    force: bool
