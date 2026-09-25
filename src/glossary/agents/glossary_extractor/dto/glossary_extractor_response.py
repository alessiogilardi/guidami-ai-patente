from pydantic import BaseModel, Field


class ExtractedEntryDto(BaseModel):
    """Un termine con la sua definizione, estratti verbatim dal testo normativo.

    Note: this docstring and the field descriptions are prompt-facing text shipped to
    the LLM (`.claude/rules/code-conventions.md`'s exception), hence Italian.
    """

    term: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "Il termine definito, copiato verbatim, senza marcatore di numerazione "
            '("1)", "a)", "A -"), senza i due punti e senza le virgolette che lo '
            "racchiudono."
        ),
    )
    definition: str = Field(
        min_length=1,
        description=(
            "La definizione del termine, copiata verbatim dal testo: tutte le frasi e i "
            "sotto-punti della voce, fino alla voce successiva, escluso il ';' o il '.' "
            "finale che le separa."
        ),
    )


class GlossaryExtractorResponse(BaseModel):
    """Elenco completo dei termini e delle relative definizioni presenti nel testo."""

    entries: list[ExtractedEntryDto] = Field(
        description=(
            "Un elemento per ogni voce definitoria del testo, nell'ordine in cui compare, "
            'escludendo le voci abrogate e quelle di solo rinvio ("cfr."). Lista vuota '
            "se il testo non contiene definizioni."
        )
    )
