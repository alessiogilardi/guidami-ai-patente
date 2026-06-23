from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel

from ._json_repository import JsonRepository


class EnrichedQuizBankRepository(JsonRepository[EnrichedQuizModel]):
    """Repository di lettura/scrittura del quiz bank enriched da/su JSON.

    `JsonRepository` deduce il tipo degli item dal parametro generico.
    """

    pass
