"""Domain exceptions of the Telegram bot."""

from .quiz_api_error import QuizApiError
from .stale_question_error import StaleQuestionError
from .unauthorized_error import UnauthorizedError

__all__ = ["QuizApiError", "StaleQuestionError", "UnauthorizedError"]
