from pydantic import BaseModel


class EmbeddableQuizVariant(BaseModel):
    """One (question, variant) text's computed embedding, before the question's DB id is known.

    Intermediate model: `question_number` is the natural key (`quiz_questions.number`),
    not the DB-generated `quiz_question_id` — resolved at store time by `StoreQuizStep`,
    mirroring `EmbeddableArticleComma` -> `ArticleCommaEntity`'s identical pattern for the
    same reason (the id does not exist until the parent row is upserted).
    """

    question_number: str
    variant: str
    embedding: list[float]
