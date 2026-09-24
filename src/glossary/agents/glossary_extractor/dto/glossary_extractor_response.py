from pydantic import BaseModel, Field


class ExtractedEntryDto(BaseModel):
    """Un termine con la sua definizione, estratti verbatim dal testo normativo.

    Note: this docstring and the field descriptions are prompt-facing text shipped to
    the LLM (`.claude/rules/code-conventions.md`'s exception), hence Italian.
    """

    term: str = Field(min_length=1, max_length=200, description="Il termine definito, verbatim.")
    definition: str = Field(
        min_length=1, description="La definizione del termine, copiata verbatim dal testo."
    )


class GlossaryExtractorResponse(BaseModel):
    """Elenco dei termini e delle relative definizioni presenti nel testo fornito."""

    entries: list[ExtractedEntryDto] = Field(
        description=(
            "Un elemento per ogni termine definito nel testo, escludendo le voci "
            "abrogate. Lista vuota se il testo non contiene definizioni."
        )
    )
