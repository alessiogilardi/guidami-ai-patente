from guidami_ai_patente_ingestor.models.quiz import QuizBankModel

from ._json_repository import JsonRepository


class QuizBankRepository(JsonRepository[QuizBankModel]):
    """Repository di lettura del quiz bank sorgente da JSON.

    `JsonRepository` deduce il tipo degli item dal parametro generico.
    """

    pass
