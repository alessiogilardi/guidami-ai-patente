from pydantic import BaseModel, ConfigDict


class GlossaryTermTranslationRequest(BaseModel):
    """`translate-glossary-terms`'s single input: retranslate every row, not only missing ones."""

    model_config = ConfigDict(frozen=True)

    force: bool
