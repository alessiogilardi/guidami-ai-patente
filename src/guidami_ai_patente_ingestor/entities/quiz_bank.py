from pydantic import BaseModel


class QuizSubQuestion(BaseModel):
    """Sotto-domanda del quiz bank, come da JSON sorgente."""

    number: str
    text: str
    correct_answer: bool
    image: str | None = None


class QuizMainQuestion(BaseModel):
    """Domanda madre del quiz bank, come da JSON sorgente."""

    question_id: int
    topic: str
    sub_questions: list[QuizSubQuestion]
