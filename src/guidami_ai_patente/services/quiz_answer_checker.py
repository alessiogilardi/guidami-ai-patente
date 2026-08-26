"""Grades a submitted answer and advertises the explanation's cache state."""

from pywire import Autowired, service

from guidami_ai_patente.enums import ExplanationStatus
from guidami_ai_patente.exceptions import QuestionNotFoundError
from guidami_ai_patente.repositories import QuizQuestionRepository

from .answer_evaluation import evaluate_answer
from .explanation_status_service import ExplanationStatusService


@service
class QuizAnswerChecker:
    """Sequences the answer lookup, the comparison and the status advertisement.

    Deliberately thin (AD-17): the comparison lives in `evaluate_answer`, which is
    unit-testable without the container, and the FR-4 rule lives in
    `ExplanationStatusService`. What is left here is the sequencing and the one
    decision that needs the question's identity — naming it in the 404.
    """

    questions: Autowired[QuizQuestionRepository]
    explanation_status: Autowired[ExplanationStatusService]

    def check(self, number: str, submitted_answer: bool) -> tuple[bool, ExplanationStatus]:
        """Grades `submitted_answer` and resolves the explanation status (FR-3, FR-4).

        Args:
            number: The question's `quiz_questions.number`.
            submitted_answer: The boolean the client answered.

        Returns:
            Whether the answer was correct, and the cache state of the question's
            comma association.

        Raises:
            QuestionNotFoundError: No question carries `number` (404).
        """
        stored_answer = self.questions.find_correct_answer(number)
        if stored_answer is None:
            raise QuestionNotFoundError(number)

        correct = evaluate_answer(stored_answer, submitted_answer)
        return correct, self.explanation_status.resolve(number)
