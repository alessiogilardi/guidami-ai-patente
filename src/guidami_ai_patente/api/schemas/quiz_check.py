"""Request and response schemas for the answer-check endpoint."""

from pydantic import BaseModel

from guidami_ai_patente.enums import ExplanationStatus


class QuizCheckRequest(BaseModel):
    """The answer the user submitted, and the session it was answered in (FR-3, FR-5)."""

    answer: bool
    session_id: str


class QuizCheckResponse(BaseModel):
    """The grade, plus which explanation affordance the client should render.

    `explanation_status` names the cache state of the question's comma association,
    not a latency: even `cached` costs a live writer call (FR-4, AD-4).
    """

    correct: bool
    explanation_status: ExplanationStatus
