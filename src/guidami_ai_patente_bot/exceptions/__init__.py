"""Domain exceptions of the Telegram bot."""

from .quiz_api_error import QuizApiError
from .session_completed_error import SessionCompletedError
from .stale_question_error import StaleQuestionError
from .unauthorized_error import UnauthorizedError

__all__ = ["QuizApiError", "SessionCompletedError", "StaleQuestionError", "UnauthorizedError"]
