"""Domain exceptions of the API, mapped to HTTP statuses by `api.exception_handlers`."""

from .explanation_unavailable_error import ExplanationUnavailableError
from .guidami_api_error import GuidamiApiError
from .labeling_not_ready_error import LabelingNotReadyError
from .question_not_found_error import QuestionNotFoundError
from .quiz_image_not_found_error import QuizImageNotFoundError
from .unregistered_user_error import UnregisteredUserError

__all__ = [
    "ExplanationUnavailableError",
    "GuidamiApiError",
    "LabelingNotReadyError",
    "QuestionNotFoundError",
    "QuizImageNotFoundError",
    "UnregisteredUserError",
]
