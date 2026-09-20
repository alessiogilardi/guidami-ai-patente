"""Output of the explanation translator: the Russian rendering."""

from pydantic import BaseModel, Field


class ExplanationTranslatorResponse(BaseModel):
    """Traduzione in russo del testo fornito, per un candidato all'esame di teoria.

    Note: the docstring and field description here are prompt-facing text shipped
    to the LLM by pydantic-ai (`output_type=ExplanationTranslatorResponse` in
    `BaseAgent`), not code documentation — hence written in Italian. See the
    Language section of `.claude/rules/code-conventions.md` for the exception.
    """

    translated_text: str = Field(
        min_length=1,
        description=(
            "La traduzione in russo del testo fornito. Mantieni invariati i "
            "riferimenti normativi (numeri di articolo e comma) e i nomi propri "
            'del codice (es. "Codice della Strada"): non tradurli né riformularli.'
        ),
    )
