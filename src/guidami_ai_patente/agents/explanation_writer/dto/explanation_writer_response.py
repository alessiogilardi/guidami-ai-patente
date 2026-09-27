"""Output of the explanation writer, with its grounding declared."""

from pydantic import BaseModel, Field, model_validator


class ExplanationWriterResponse(BaseModel):
    """Spiegazione del perché la risposta corretta a un quiz è quella indicata.

    La spiegazione si fonda esclusivamente sui commi normativi numerati forniti: non
    deve contenere norme, numeri di articolo, sanzioni o eccezioni che non compaiano
    nel testo di quei commi.

    Note: the docstring and field descriptions here are prompt-facing text shipped to
    the LLM by pydantic-ai (`output_type=ExplanationWriterResponse` in `BaseAgent`),
    not code documentation — hence written in Italian. See the Language section of
    `.claude/rules/code-conventions.md` for the exception.
    """

    explanation: str = Field(
        min_length=1,
        description=(
            "La spiegazione rivolta al candidato, in italiano semplice, al massimo "
            "tre frasi brevi. Inizia direttamente dalla regola, senza commentare la "
            "risposta del candidato. Non citare il fatto che i commi provengono da una "
            "ricerca: per il candidato esistono solo la domanda e la norma."
        ),
    )
    cited_comma_numbers: list[int] = Field(
        min_length=1,
        description=(
            "Gli ordinali dei commi che hai effettivamente usato nella spiegazione, "
            "almeno uno. Non indicare mai un ordinale che non compare nell'elenco dei "
            "commi forniti, e non ripetere lo stesso ordinale due volte."
        ),
    )

    @model_validator(mode="after")
    def _reject_repeated_ordinals(self) -> "ExplanationWriterResponse":
        """Rejects a repeated ordinal so pydantic-ai retries (AD-14).

        The range check — every ordinal within the supplied set — cannot live here:
        this model cannot see how many commas were supplied. `ExplanationService`
        owns it, exactly as `_resolve_labels` owns the judge's.
        """
        if len(set(self.cited_comma_numbers)) != len(self.cited_comma_numbers):
            raise ValueError("cited_comma_numbers must not repeat an ordinal")
        return self
