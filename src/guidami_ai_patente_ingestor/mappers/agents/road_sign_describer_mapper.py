from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel


class RoadSignDescriberMapper:
    """Bidirectional translation between `EnrichedQuizModel` and the describer agent's DTOs.

    All methods are static and pure (no injected dependencies).
    """

    @staticmethod
    def from_enriched_quiz_to_request(question: EnrichedQuizModel) -> RoadSignDescriberRequest:
        """Builds the agent request from an enriched sub-question.

        Args:
            question: Quiz bank sub-question with topic and text.

        Returns:
            `RoadSignDescriberRequest` with the question's topic and text as context.
        """
        return RoadSignDescriberRequest(topic=question.topic, text=question.text)

    @staticmethod
    def from_response_to_enriched_quiz(
        question: EnrichedQuizModel,
        response: RoadSignDescriberResponse,
    ) -> EnrichedQuizModel:
        """Applies the description produced by the agent to the enriched sub-question.

        Args:
            question: Original sub-question to apply the description to.
            response: Structured agent response with the sign's name and description.

        Returns:
            New `EnrichedQuizModel` with `image_description` populated.
        """
        description = f"{response.name}. {response.description}"
        return question.model_copy(update={"image_description": description})
