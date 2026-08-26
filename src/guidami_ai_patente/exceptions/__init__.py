"""Domain exceptions of the API, mapped to HTTP statuses by `api.exception_handlers`."""

from .guidami_api_error import GuidamiApiError
from .question_not_found_error import QuestionNotFoundError
from .quiz_image_not_found_error import QuizImageNotFoundError

__all__ = ["GuidamiApiError", "QuestionNotFoundError", "QuizImageNotFoundError"]
