from pydantic import BaseModel


class RoadSignDescriberResponse(BaseModel):
    """Output strutturato dell'agente di descrizione dei segnali stradali.

    L'ordine dei campi codifica la sequenza di Chain-of-Thought imposta da
    pydantic-ai tramite `output_type`: il modello ragiona per iscritto in
    `visual_analysis` prima di sintetizzare `name` e `description`.

    Attributes:
        visual_analysis: Ragionamento visivo interno (Chain-of-Thought) sul
            contenuto dell'immagine. Non viene persistito né incluso in
            `image_description`: è scartato a valle da `RoadSignDescriberMapper`,
            che legge solo `name` e `description`.
        name: Nome del segnale stradale.
        description: Descrizione dettagliata del segnale.
    """

    visual_analysis: str
    name: str
    description: str
