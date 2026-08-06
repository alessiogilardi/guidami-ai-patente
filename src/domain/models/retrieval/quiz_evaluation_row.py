from pydantic import BaseModel


class QuizEvaluationRow(BaseModel):
    """A quiz question as read by the evaluation harness.

    Unlike the write-side `QuizQuestionEntity`, this read model carries `id` (a
    DB-generated column) because `quiz_question_embeddings.quiz_question_id` joins on
    it. `embedding` is required, with no default: `QuizReadRepository.fetch_with_vectors`
    (T-4) performs an `INNER JOIN`, so a question with no vector for the requested
    variant is absent from the result, never present with an empty/null one. A default
    would make that impossible state representable again and push every downstream
    consumer into defending against it.
    """

    id: int
    number: str
    topic: str
    text: str
    correct_answer: bool
    exact_keywords: list[str] | None
    image_filename: str | None
    embedding: list[float]
