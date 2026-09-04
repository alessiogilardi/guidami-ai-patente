"""Grades a submitted answer and advertises the explanation's cache state."""

from pywire import Autowired, service

from commons.use_cases import UseCase
from guidami_ai_patente.enums import ExplanationStatus
from guidami_ai_patente.exceptions import QuestionNotFoundError
from guidami_ai_patente.models import QuizAnswerCheckRequest
from guidami_ai_patente.repositories import QuizQuestionRepository

from .answer_evaluation import evaluate_answer
from .explanation_status_service import ExplanationStatusService


@service
class QuizAnswerChecker(UseCase[QuizAnswerCheckRequest, tuple[bool, ExplanationStatus]]):
    """Sequences the answer lookup, the comparison and the status advertisement.

    Deliberately thin (AD-17): the comparison lives in `evaluate_answer`, which is
    unit-testable without the container, and the FR-4 rule lives in
    `ExplanationStatusService`. What is left here is the sequencing and the one
    decision that needs the question's identity — naming it in the 404.
    """

    questions: Autowired[QuizQuestionRepository]
    explanation_status: Autowired[ExplanationStatusService]

    def execute(self, request: QuizAnswerCheckRequest) -> tuple[bool, ExplanationStatus]:
        """Grades the submitted answer and resolves the explanation status (FR-3, FR-4).

        Raises:
            QuestionNotFoundError: No question carries `request.number` (404).
        """
        stored_answer = self.questions.find_correct_answer(request.number)
        if stored_answer is None:
            raise QuestionNotFoundError(request.number)

        correct = evaluate_answer(stored_answer, request.submitted_answer)
        return correct, self.explanation_status(request.number)
