"""Maps the internal session summary onto the wire contract."""

from guidami_ai_patente.api.schemas.quiz_answers import (
    SessionSummaryResponse,
    TopicSummaryResponse,
    WrongQuestionResponse,
)
from guidami_ai_patente.models import SessionSummary


class SessionSummaryMapper:
    """Turns a `SessionSummary` into the response the client receives.

    A field-for-field copy, kept as its own mapper so the wire contract stays a separate
    type from the domain model even while the two happen to share a shape. Static, like
    every mapper in this repo.
    """

    @staticmethod
    def from_summary_to_response(summary: SessionSummary) -> SessionSummaryResponse:
        """Builds the wire response, nested breakdowns included."""
        return SessionSummaryResponse(
            answered=summary.answered,
            correct=summary.correct,
            by_topic=[
                TopicSummaryResponse(
                    topic=topic.topic, answered=topic.answered, correct=topic.correct
                )
                for topic in summary.by_topic
            ],
            wrong_questions=[
                WrongQuestionResponse(number=question.number, text=question.text)
                for question in summary.wrong_questions
            ],
        )
