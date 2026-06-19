from guidami_ai_patente_ingestor.entities import QuizMainQuestion

from ._json_repository import JsonRepository


class QuizBankRepository(JsonRepository[QuizMainQuestion]):
    """Nessun __init__ necessario! JsonRepository capirà da solo
    che deve usare `Article` leggendo le parentesi quadre.
    """

    pass
