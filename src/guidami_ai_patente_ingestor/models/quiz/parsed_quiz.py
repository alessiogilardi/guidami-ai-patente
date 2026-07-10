from pydantic import BaseModel


class ParsedQuizItemModel(BaseModel):
    """Sub-question extracted from the question bank PDF, as found in the source JSON."""

    number: str
    text: str
    correct_answer: bool
    image: str | None = None


class ParsedQuizModel(BaseModel):
    """Main question extracted from the PDF, with its associated sub-questions."""

    question_id: int
    topic: str
    sub_questions: list[ParsedQuizItemModel]
