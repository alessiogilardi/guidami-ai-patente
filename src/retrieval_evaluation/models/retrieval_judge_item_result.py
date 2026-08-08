from pydantic import BaseModel

from domain.models.retrieval import RetrievedComma


class RetrievalJudgeItemResult(BaseModel):
    """One judged quiz question: its full context, the retrieval, and the agent's verdict.

    Attributes:
        quiz_number: Natural key of the judged `quiz_questions` row.
        topic: Topic of the judged question.
        text: Text of the judged question.
        correct_answer: Correct answer to the question.
        image_filename: Filename of the image attached to the question, if any.
        image_description: LLM-generated description of the attached image, if any.
        retrieved_commas: Top-k commas retrieved for this question by dense retrieval,
            in the same order they were shown to the judge.
        is_clear: Whether the retrieved commas clearly and unambiguously justify the
            quiz's correct answer, per the agent's judgment.
        rationale: The agent's short explanation for `is_clear`.
    """

    quiz_number: str
    topic: str
    text: str
    correct_answer: bool
    image_filename: str | None
    image_description: str | None
    retrieved_commas: list[RetrievedComma]
    is_clear: bool
    rationale: str
