"""Maps the internal question projection onto the wire contract."""

from guidami_ai_patente.api.schemas.quiz_question import QuizQuestionResponse
from guidami_ai_patente.models import QuizQuestionSummary

QUIZ_IMAGE_URL_PREFIX = "/quiz-images/"
"""The FR-12 endpoint's path prefix, declared once and reused by its router."""


class QuizQuestionMapper:
    """Turns a `QuizQuestionSummary` into the response the client receives.

    The only transformation is `image_filename` → `image_url`: the database stores a
    content-hash filename with no path structure, and the client should not have to
    know how to turn one into a request. Static, like every mapper in this repo.
    """

    @staticmethod
    def from_summary_to_response(summary: QuizQuestionSummary) -> QuizQuestionResponse:
        """Builds the wire response, resolving the image endpoint path."""
        image_url = (
            None
            if summary.image_filename is None
            else f"{QUIZ_IMAGE_URL_PREFIX}{summary.image_filename}"
        )
        return QuizQuestionResponse(
            number=summary.number,
            topic=summary.topic,
            text=summary.text,
            image_url=image_url,
        )
