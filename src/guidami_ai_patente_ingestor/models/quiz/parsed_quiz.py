from pydantic import BaseModel


class ParsedQuizItemModel(BaseModel):
    """Sotto-domanda estratta dal PDF del banco delle domande, come da JSON sorgente."""

    number: str
    text: str
    correct_answer: bool
    image: str | None = None


class ParsedQuizModel(BaseModel):
    """Domanda principale estratta dal PDF, con le sotto-domande associate."""

    question_id: int
    topic: str
    sub_questions: list[ParsedQuizItemModel]
