"""The stateless half of answer checking."""

from guidami_ai_patente.exceptions import QuestionNotFoundError


def evaluate_answer(stored_answer: bool | None, submitted_answer: bool) -> bool:
    """Compares a submitted answer against the stored one (FR-3).

    A plain function rather than a method so the comparison is testable without the
    container at all (AD-17): pywire caches singletons, so a test that constructs a
    second `QuizAnswerChecker` with a double gets the first one back, and the
    assertion silently describes the wrong object.

    Args:
        stored_answer: The persisted `correct_answer`, or `None` when no row matched.
        submitted_answer: The boolean the client sent.

    Returns:
        Whether the submitted answer matches the stored one.

    Raises:
        QuestionNotFoundError: No question carries the requested number. Raised here
            rather than returned as a third state so the caller cannot forget to
            branch on it — the global handler turns it into a 404.
    """
    if stored_answer is None:
        raise QuestionNotFoundError("<unknown>")
    return stored_answer == submitted_answer
