from pydantic import BaseModel


class CleanedQuizModel(BaseModel):
    """Quiz bank sub-question, flattened and deduplicated, self-contained."""

    question_id: int
    topic: str
    number: str
    text: str
    correct_answer: bool
    image: str | None = None
