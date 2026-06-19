from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle

from ._json_repository import JsonRepository


class EnrichedArticleRepository(JsonRepository[EnrichedArticle]):
    """Nessun __init__ necessario! JsonRepository capirà da solo
    che deve usare `Article` leggendo le parentesi quadre.
    """

    pass
