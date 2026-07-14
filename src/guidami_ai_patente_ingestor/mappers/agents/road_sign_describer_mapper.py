from commons.utils import deduplicate
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel, ImageAnalysis


class RoadSignDescriberMapper:
    """Bidirectional translation between `EnrichedQuizModel` and the describer agent's DTOs.

    All methods are static and pure (no injected dependencies).
    """

    @staticmethod
    def from_enriched_quizzes_to_request(
        questions: list[EnrichedQuizModel],
    ) -> RoadSignDescriberRequest:
        """Builds a single request from every quiz that references the same image.

        Duplicate (topic, text) pairs are collapsed (first-seen order) so the prompt
        lists each distinct context once.

        Args:
            questions: Quiz bank sub-questions that all reference the same image.

        Returns:
            `RoadSignDescriberRequest` with one context per distinct (topic, text).
        """
        unique = deduplicate(questions, key=lambda q: (q.topic, q.text))
        contexts = [f"Argomento: {q.topic} — Testo: {q.text}" for q in unique]
        return RoadSignDescriberRequest(contexts=contexts)

    @staticmethod
    def from_response_to_enriched_quiz(
        question: EnrichedQuizModel,
        response: RoadSignDescriberResponse,
    ) -> EnrichedQuizModel:
        """Applies the description produced by the agent to the enriched sub-question.

        Sets `image_description` (flat, downstream) and `image_analysis` (structured,
        debug-only, includes `visual_analysis`).

        Args:
            question: Original sub-question to apply the description to.
            response: Structured agent response with the sign's name and description.

        Returns:
            New `EnrichedQuizModel` with `image_description` and `image_analysis` populated.
        """
        description = f"{response.name}. {response.description}"
        analysis = ImageAnalysis(
            visual_analysis=response.visual_analysis,
            name=response.name,
            description=response.description,
        )
        return question.model_copy(
            update={"image_description": description, "image_analysis": analysis}
        )
