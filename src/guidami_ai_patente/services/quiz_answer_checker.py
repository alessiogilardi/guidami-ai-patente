"""Grades a submitted answer, persists it, and advertises the explanation's cache state."""

from pywire import Autowired, service

from commons.use_cases import UseCase
from guidami_ai_patente.enums import ExplanationStatus
from guidami_ai_patente.exceptions import QuestionNotFoundError
from guidami_ai_patente.models import QuizAnswerCheckRequest
from guidami_ai_patente.repositories import QuizAnswerRepository, QuizQuestionRepository

from .answer_evaluation import evaluate_answer
from .explanation_status_service import ExplanationStatusService


@service
class QuizAnswerChecker(UseCase[QuizAnswerCheckRequest, tuple[bool, ExplanationStatus]]):
    """Sequences the answer lookup, persistence, the comparison and the status advertisement.

    Persistence (`answers.record_answer`) happens in the same call as grading, never
    as a separate round trip (spec 0016, AD-7): if it raises, the whole request fails
    and no response is returned as though grading alone had succeeded.
    """

    questions: Autowired[QuizQuestionRepository]
    explanation_status: Autowired[ExplanationStatusService]
    answers: Autowired[QuizAnswerRepository]

    def execute(self, request: QuizAnswerCheckRequest) -> tuple[bool, ExplanationStatus]:
        """Grades the submitted answer, records it, and resolves the explanation status.

        Raises:
            QuestionNotFoundError: No question carries `request.number` (404).
        """
        stored_answer = self.questions.find_correct_answer(request.number)
        if stored_answer is None:
            raise QuestionNotFoundError(request.number)

        correct = evaluate_answer(stored_answer, request.submitted_answer)
        self.answers.record_answer(
            request.telegram_user_id, request.number, request.session_id, request.submitted_answer
        )
        return correct, self.explanation_status(request.number)
