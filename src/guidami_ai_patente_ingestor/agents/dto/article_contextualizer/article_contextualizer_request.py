from pydantic import BaseModel


class ArticleContextualizerRequest(BaseModel):
    """Input per l'agente di contestualizzazione degli articoli normativi.

    Attributes:
        title: Titolo dell'articolo.
        text: Testo principale dell'articolo.
        paragraphs: Commi pre-formattati come stringa numerata (es. "1. ...", "2. ...").
    """

    title: str
    text: str
    paragraphs: str
