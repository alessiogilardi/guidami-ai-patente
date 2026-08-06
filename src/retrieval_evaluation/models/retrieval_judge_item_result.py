from pydantic import BaseModel


class RetrievalJudgeItemResult(BaseModel):
    """One judged quiz question: the agent's verdict plus its rationale.

    Attributes:
        quiz_number: Natural key of the judged `quiz_questions` row.
        is_clear: Whether the retrieved commas clearly and unambiguously justify the
            quiz's correct answer, per the agent's judgment.
        rationale: The agent's short explanation for `is_clear`.
    """

    quiz_number: str
    is_clear: bool
    rationale: str
