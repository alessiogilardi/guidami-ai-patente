"""The stateless half of answer checking."""


def evaluate_answer(stored_answer: bool, submitted_answer: bool) -> bool:
    """Compares a submitted answer against the stored one (FR-3).

    A plain function rather than a method so the comparison is testable without the
    container at all (AD-17): pywire caches singletons, so a test that constructs a
    second `QuizAnswerChecker` with a double gets the first one back, and the
    assertion silently describes the wrong object.

    Args:
        stored_answer: The persisted `correct_answer`.
        submitted_answer: The boolean the client sent.

    Returns:
        Whether the submitted answer matches the stored one.
    """
    return stored_answer == submitted_answer
