from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizMainQuestion

from ._json_repository import JsonRepository


class EnrichedQuizBankRepository(JsonRepository[EnrichedQuizMainQuestion]):
    """Nessun __init__ necessario! JsonRepository capirà da solo
    che deve usare `Article` leggendo le parentesi quadre.
    """

    pass
