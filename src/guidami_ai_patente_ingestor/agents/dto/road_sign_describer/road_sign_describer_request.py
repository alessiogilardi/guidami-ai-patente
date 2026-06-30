from pydantic import BaseModel


class RoadSignDescriberRequest(BaseModel):
    """Input per l'agente di descrizione dei segnali stradali.

    Attributes:
        topic: Argomento della domanda del quiz (fornisce contesto alla descrizione).
        text: Testo della domanda del quiz (fornisce contesto alla descrizione).
    """

    topic: str
    text: str
