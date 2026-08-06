from pydantic import BaseModel, Field


class RetrievalJudgeResponse(BaseModel):
    """Giudizio sulla qualità del retrieval per un singolo quiz.

    Valuta se i commi recuperati spiegano in modo chiaro e inequivocabile il motivo
    per cui la risposta al quiz è vera o falsa.

    Note: the docstring and field descriptions below are prompt-facing text shipped
    to the LLM by pydantic-ai (`output_type=RetrievalJudgeResponse` in `BaseAgent`),
    not code documentation — hence written in Italian. See the Language section of
    `.claude/rules/code-conventions.md` for the exception.
    """

    is_clear: bool = Field(
        description=(
            "True se i commi recuperati spiegano in modo chiaro e inequivocabile "
            "perché la risposta al quiz è vera o falsa, False altrimenti."
        )
    )
    rationale: str = Field(
        description=(
            "Breve motivazione del giudizio: se True, quale comma spiega la regola; "
            "se False, cosa manca o è ambiguo. Circa 30 parole."
        ),
        max_length=500,
    )
