from pydantic import BaseModel, Field, field_validator


class TranslatedTermItemDto(BaseModel):
    """La resa russa ufficiale del termine, in materia di circolazione stradale.

    Note: prompt-facing text (`.claude/rules/code-conventions.md`'s exception).
    """

    term_ru: str = Field(min_length=1, max_length=80)

    @field_validator("term_ru")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """Rejects a whitespace-only translation `min_length=1` alone would let through."""
        if not value.strip():
            raise ValueError("term_ru must not be blank")
        return value


class GlossaryTermTranslatorResponse(BaseModel):
    """Le rese russe, una per ogni termine del lotto, nello stesso ordine."""

    translations: list[TranslatedTermItemDto] = Field(min_length=1)
