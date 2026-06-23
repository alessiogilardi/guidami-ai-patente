from pydantic import BaseModel


class EnrichedQuizItemModel(BaseModel):
    """Sotto-domanda del quiz bank enriched, con `image_description` inline."""

    number: str
    text: str
    correct_answer: bool
    image: str | None = None
    image_description: str | None = None


class EnrichedQuizModel(BaseModel):
    """Domanda madre del quiz bank enriched."""

    question_id: int
    topic: str
    sub_questions: list[EnrichedQuizItemModel]
