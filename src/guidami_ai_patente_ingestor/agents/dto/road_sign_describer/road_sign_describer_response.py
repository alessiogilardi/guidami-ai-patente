from pydantic import BaseModel


class RoadSignDescriberResponse(BaseModel):
    """Output strutturato dell'agente di descrizione dei segnali stradali.

    Attributes:
        name: Nome del segnale stradale.
        description: Descrizione dettagliata del segnale.
    """

    name: str
    description: str
