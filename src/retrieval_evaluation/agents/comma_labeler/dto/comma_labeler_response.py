from pydantic import BaseModel, Field, model_validator


class CommaLabelerResponse(BaseModel):
    """Etichettatura dei commi che giustificano la risposta corretta a un quiz.

    Identifica quali, tra i commi numerati presentati, giustificano la risposta
    corretta al quiz, in ordine dal più al meno pertinente.

    Note: the docstring and field descriptions below are prompt-facing text shipped
    to the LLM by pydantic-ai (`output_type=CommaLabelerResponse` in `BaseAgent`),
    not code documentation — hence written in Italian. See the Language section of
    `.claude/rules/code-conventions.md` for the exception.
    """

    comma_numbers: list[int] = Field(
        max_length=3,
        description=(
            "Gli ordinali (numeri) dei commi presentati che giustificano la risposta "
            "corretta, al massimo tre, ordinati dal più al meno pertinente — questo "
            "ordine viene salvato come judge_rank. Una lista vuota significa che "
            "nessun comma giustifica la risposta. Lo stesso numero non deve mai "
            "comparire due volte."
        ),
    )
    rationale: str = Field(
        min_length=1,
        max_length=1000,
        description=(
            "Motivazione della scelta, richiesta in ogni caso: se la lista è vuota, "
            "spiega perché nessun comma giustifica la risposta; altrimenti spiega "
            "perché i commi indicati la giustificano. Sii conciso: massimo 2-3 frasi, "
            "non oltre 1000 caratteri."
        ),
    )

    @model_validator(mode="after")
    def _reject_repeated_numbers(self) -> "CommaLabelerResponse":
        """Rejects a repeated ordinal so pydantic-ai retries instead of the write path."""
        if len(set(self.comma_numbers)) != len(self.comma_numbers):
            raise ValueError("comma_numbers must not repeat a candidate number")
        return self
