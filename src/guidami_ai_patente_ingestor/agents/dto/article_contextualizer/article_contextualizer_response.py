from pydantic import BaseModel


class ArticleContextualizerResponse(BaseModel):
    """Output strutturato dell'agente di contestualizzazione.

    Attributes:
        contexts: Dizionario `{comma_index: testo_di_contesto}` per ogni comma
            dell'articolo. Le chiavi sono interi (indici dei commi a partire da 0).
    """

    contexts: dict[int, str]
