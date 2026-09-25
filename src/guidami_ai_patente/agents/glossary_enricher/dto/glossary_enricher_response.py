"""Output of the on-demand glossary enricher (FR-1, FR-3, AD-3)."""

from pydantic import BaseModel, Field, model_validator


class GlossaryEnricherEntryDto(BaseModel):
    """Un termine tecnico della domanda con una sua definizione.

    Note: prompt-facing text shipped to the LLM by pydantic-ai, hence Italian
    (`.claude/rules/code-conventions.md`).
    """

    term: str = Field(
        min_length=1,
        max_length=80,
        description="Il termine tecnico, così come compare nella domanda.",
    )
    definition: str = Field(
        min_length=1, description="La definizione del termine, in italiano semplice."
    )


class GlossaryEnricherResponse(BaseModel):
    """Elenco dei termini tecnici della domanda, con una definizione per ciascuno."""

    entries: list[GlossaryEnricherEntryDto] = Field(
        default_factory=list,
        description=(
            "Un elemento per ogni termine tecnico della domanda. Lista vuota se la "
            "domanda non contiene alcun termine tecnico."
        ),
    )

    @model_validator(mode="after")
    def _reject_repeated_terms(self) -> "GlossaryEnricherResponse":
        """Rejects a duplicate normalized term so pydantic-ai retries (AD-3, AD-6).

        `term.strip().casefold()` is the same normalization rule used everywhere else a
        term is compared in the vocabulary stage (AD-6, spec 0021 second grilling
        round) — not bare `casefold()`.
        """
        keys = [entry.term.strip().casefold() for entry in self.entries]
        if len(set(keys)) != len(keys):
            raise ValueError("entries must not repeat the same term")
        return self
