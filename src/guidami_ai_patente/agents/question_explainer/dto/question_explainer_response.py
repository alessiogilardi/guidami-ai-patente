"""Output of the vocabulary explainer, with its grounding declared (FR-6)."""

from pydantic import BaseModel, Field, model_validator


class QuestionExplainerResponse(BaseModel):
    """Spiegazione del significato della domanda e dei termini tecnici che contiene.

    Note: prompt-facing text shipped to the LLM by pydantic-ai, hence Italian
    (`.claude/rules/code-conventions.md`).
    """

    explanation: str = Field(
        min_length=1,
        max_length=900,
        description=(
            "La spiegazione della domanda in italiano semplice, al massimo quattro "
            "frasi. Metti tra virgolette caporali «così» ogni termine che citi da uno "
            "dei candidati forniti, alla sua prima occorrenza. Un termine che spieghi "
            "di tua conoscenza, senza un candidato corrispondente, va scritto in prosa "
            "semplice senza virgolette."
        ),
    )
    cited_term_numbers: list[int] = Field(
        default_factory=list,
        description=(
            "Gli ordinali dei candidati che hai effettivamente citato tra virgolette "
            "caporali nella spiegazione. Può essere vuoto se la domanda non usa termini "
            "tecnici. Non ripetere mai lo stesso ordinale."
        ),
    )

    @model_validator(mode="after")
    def _reject_repeated_ordinals(self) -> "QuestionExplainerResponse":
        if len(set(self.cited_term_numbers)) != len(self.cited_term_numbers):
            raise ValueError("cited_term_numbers must not repeat an ordinal")
        return self
