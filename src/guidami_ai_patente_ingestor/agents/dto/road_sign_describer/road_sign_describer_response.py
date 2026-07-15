from pydantic import BaseModel, Field


class RoadSignDescriberResponse(BaseModel):
    """Output strutturato dell'agente di descrizione dei segnali stradali.

    L'ordine dei campi codifica la sequenza di Chain-of-Thought imposta da
    pydantic-ai tramite `output_type`: il modello ragiona per iscritto in
    `visual_analysis` prima di sintetizzare `name` e `description`.

    Note: the docstring and field descriptions below are prompt-facing text
    shipped to the LLM by pydantic-ai (`output_type=RoadSignDescriberResponse`
    in `BaseAgent`), not code documentation — hence written in Italian. See the
    Language section of `.claude/rules/code-conventions.md` for the exception.

    Attributes:
        visual_analysis: Ragionamento visivo interno (Chain-of-Thought) sul
            contenuto dell'immagine. Non persistito né incluso in
            `image_description`: viene scartato a valle da
            `RoadSignDescriberMapper`, che legge solo `name` e `description`.
        name: Nome del segnale stradale.
        description: Descrizione dettagliata del segnale.
    """

    visual_analysis: str = Field(
        description=(
            "Ragionamento visivo passo-passo (Chain-of-Thought) sul contenuto "
            "dell'immagine, prima di sintetizzare nome e descrizione del segnale. "
            "Campo interno, non persistito a valle."
        )
    )
    name: str = Field(description="Nome ufficiale del segnale stradale raffigurato.")
    description: str = Field(
        description="Descrizione dettagliata del segnale stradale raffigurato."
    )
