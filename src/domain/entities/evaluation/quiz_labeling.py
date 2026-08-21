from pydantic import BaseModel


class QuizLabelingEntity(BaseModel):
    """Row of the `quiz_labelings` table (see db/init.sql).

    `id` and `created_at` are DB-generated and have no corresponding field here. A
    labeling's outcome is derived by counting its `quiz_comma_labels` children, not
    stored on this row: zero children means the corpus does not justify the question,
    while a missing `quiz_labelings` row for a question means it was never labeled
    (AD-6).
    """

    run_id: int
    quiz_question_id: int
    rationale: str
