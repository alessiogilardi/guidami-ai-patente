from pydantic import BaseModel, Field, field_validator


class SimplifiedDefinitionItemDto(BaseModel):
    """La stessa definizione legale, riscritta in italiano semplice e comprensibile.

    Note: prompt-facing text (`.claude/rules/code-conventions.md`'s exception).
    `max_length=400` è un backstop meccanico (spec 0022 FR-3): la riscrittura deve
    restare 1-2 frasi brevi, non un paragrafo.
    """

    definition_plain: str = Field(min_length=1, max_length=400)

    @field_validator("definition_plain")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """Rejects a whitespace-only rewrite `min_length=1` alone would let through."""
        if not value.strip():
            raise ValueError("definition_plain must not be blank")
        return value


class GlossaryDefinitionSimplifierResponse(BaseModel):
    """Le riscritture in italiano semplice, una per definizione, nello stesso ordine."""

    simplifications: list[SimplifiedDefinitionItemDto] = Field(min_length=1)
