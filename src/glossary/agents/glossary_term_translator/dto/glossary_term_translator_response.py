from pydantic import BaseModel, Field


class TranslatedTermItemDto(BaseModel):
    """La resa russa ufficiale del termine, in materia di circolazione stradale.

    Note: prompt-facing text (`.claude/rules/code-conventions.md`'s exception).
    """

    term_ru: str = Field(min_length=1, max_length=80)


class GlossaryTermTranslatorResponse(BaseModel):
    """Le rese russe, una per ogni termine del lotto, nello stesso ordine."""

    translations: list[TranslatedTermItemDto] = Field(min_length=1)
