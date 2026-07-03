from pydantic import BaseModel, Field


class NormReferenceDescriberRequest(BaseModel):
    """Input per l'agente di generazione dei metadati normativi di un quiz.

    Attributes:
        topic: Argomento della domanda del quiz.
        text: Testo della domanda del quiz.
        correct_answer: Risposta corretta alla domanda.
        image_description: Descrizione dell'immagine allegata (se presente).
    """

    topic: str = Field(min_length=1)
    text: str = Field(min_length=1)
    correct_answer: bool
    image_description: str | None = None
