from domain.entities.quiz import QuizMetadata
from guidami_ai_patente_ingestor.agents.dto.norm_reference_describer import (
    NormReferenceDescriberRequest,
    NormReferenceDescriberResponse,
)
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel


class NormReferenceDescriberMapper:
    """Traduzione bidirezionale tra `EnrichedQuizModel` e i DTO dell'agente NormReferenceDescriber.

    Tutti i metodi sono statici e puri (nessuna dipendenza iniettata).
    """

    @staticmethod
    def from_enriched_quiz_to_request(
        question: EnrichedQuizModel,
    ) -> NormReferenceDescriberRequest:
        """Costruisce la request dell'agente a partire da una sotto-domanda enriched.

        Args:
            question: Sotto-domanda del quiz bank con topic, testo e risposta corretta.

        Returns:
            `NormReferenceDescriberRequest` con i campi prompt-rilevanti.
        """
        return NormReferenceDescriberRequest(
            topic=question.topic,
            text=question.text,
            correct_answer=question.correct_answer,
            image_description=question.image_description,
        )

    @staticmethod
    def from_response_to_enriched_quiz(
        question: EnrichedQuizModel,
        response: NormReferenceDescriberResponse,
    ) -> EnrichedQuizModel:
        """Applica i metadati normativi prodotti dall'agente alla sotto-domanda enriched.

        Args:
            question: Sotto-domanda originale su cui applicare i metadati.
            response: Risposta strutturata dell'agente con i metadati normativi.

        Returns:
            Nuova `EnrichedQuizModel` con `quiz_metadata` valorizzato.
        """
        return question.model_copy(
            update={
                "quiz_metadata": QuizMetadata(
                    core_concepts=response.core_concepts,
                    entities=response.entities,
                    exact_keywords=response.exact_keywords,
                    vector_search_queries=response.vector_search_queries,
                    rule_explanation=response.rule_explanation,
                )
            }
        )
