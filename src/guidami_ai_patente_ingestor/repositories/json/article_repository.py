from guidami_ai_patente_ingestor.entities import Article

from ._json_repository import JsonRepository


class ArticleRepository(JsonRepository[Article]):
    """Nessun __init__ necessario! JsonRepository capirà da solo
    che deve usare `Article` leggendo le parentesi quadre.
    """

    pass
