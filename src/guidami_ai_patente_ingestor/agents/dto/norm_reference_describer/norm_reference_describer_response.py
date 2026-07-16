from pydantic import BaseModel, Field


class NormReferenceDescriberResponse(BaseModel):
    """Output strutturato dell'analisi di un quiz per la patente.

    Contiene i metadati semantici normativi usati in un sistema RAG per
    recuperare gli articoli del Codice della Strada (CdS) e del Codice delle
    Assicurazioni Private (CAP).

    Note: the docstring and field descriptions below are prompt-facing text
    shipped to the LLM by pydantic-ai (`output_type=NormReferenceDescriberResponse`
    in `BaseAgent`), not code documentation — hence written in Italian. See the
    Language section of `.claude/rules/code-conventions.md` for the exception.
    """

    core_concepts: list[str] = Field(
        description=(
            "2-3 concetti normativi generali alla base del quiz "
            "(es. 'Obbligo di precedenza', 'Limiti di velocità')."
        ),
        min_length=2,
        max_length=3,
    )

    exact_keywords: list[str] = Field(
        description=(
            "3-5 parole chiave o termini tecnici esatti usati nel testo ufficiale "
            "del Codice della Strada o del CAP."
        ),
        min_length=3,
        max_length=5,
    )

    vector_search_queries: list[str] = Field(
        description=(
            "2-3 frasi formulate per massimizzare l'efficacia di una ricerca "
            "semantica vettoriale nel testo normativo del CdS o del CAP."
        ),
        min_length=2,
        max_length=3,
    )

    rule_explanation: str = Field(
        description=(
            "Breve spiegazione del principio normativo applicato nel quiz. "
            "Circa 30 parole, concisa e tecnica."
        ),
        # Safety net against runaway hallucinations, not a normal-length constraint.
        max_length=500,
    )
