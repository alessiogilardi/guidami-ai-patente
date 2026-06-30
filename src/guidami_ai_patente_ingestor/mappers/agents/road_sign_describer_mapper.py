from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel


class RoadSignDescriberMapper:
    """Traduzione bidirezionale tra `EnrichedQuizModel` e i DTO dell'agente descrittore.

    Tutti i metodi sono statici e puri (nessuna dipendenza iniettata).
    """

    @staticmethod
    def from_enriched_quiz_to_request(question: EnrichedQuizModel) -> RoadSignDescriberRequest:
        """Costruisce la request dell'agente a partire da una sotto-domanda enriched.

        Args:
            question: Sotto-domanda del quiz bank con topic e testo.

        Returns:
            `RoadSignDescriberRequest` con topic e testo della domanda come contesto.
        """
        return RoadSignDescriberRequest(topic=question.topic, text=question.text)

    @staticmethod
    def from_response_to_enriched_quiz(
        question: EnrichedQuizModel,
        response: RoadSignDescriberResponse,
    ) -> EnrichedQuizModel:
        """Applica la descrizione prodotta dall'agente alla sotto-domanda enriched.

        Args:
            question: Sotto-domanda originale su cui applicare la descrizione.
            response: Risposta strutturata dell'agente con nome e descrizione del segnale.

        Returns:
            Nuova `EnrichedQuizModel` con `image_description` valorizzato.
        """
        description = f"{response.name}. {response.description}"
        return question.model_copy(update={"image_description": description})
