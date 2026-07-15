from pydantic import BaseModel, Field


class ArticleContextualizerResponse(BaseModel):
    """Output strutturato dell'agente di contestualizzazione degli articoli.

    Note: the docstring and field descriptions below are prompt-facing text
    shipped to the LLM by pydantic-ai (`output_type=ArticleContextualizerResponse`
    in `BaseAgent`), not code documentation — hence written in Italian. See the
    Language section of `.claude/rules/code-conventions.md` for the exception.

    Attributes:
        contexts: Dizionario `{comma_index: context_text}` per ogni comma
            dell'articolo. Le chiavi sono interi (indice del comma a partire da 0).
    """

    contexts: dict[int, str] = Field(
        description=(
            "Mappa comma_index -> testo di contesto: per ogni comma dell'articolo "
            "(indice intero a partire da 0), il testo che ne chiarisce il significato "
            "nell'ambito dell'articolo."
        )
    )
