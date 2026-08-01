from pydantic import BaseModel


class QuizQuestionEntity(BaseModel):
    """Row of the `quiz_questions` table (see db/init.sql).

    Retrieval metadata (`core_concepts`, `exact_keywords`, `rule_explanation`)
    is flattened onto the entity: all three are `None` together when no
    metadata was generated for the question. `created_at` is DB-managed
    (`DEFAULT now()`) and has no corresponding field here.
    """

    number: str
    question_id: int
    topic: str
    text: str
    correct_answer: bool
    image_filename: str | None = None
    core_concepts: list[str] | None = None
    exact_keywords: list[str] | None = None
    rule_explanation: str | None = None
    embedding: list[float] | None = None
