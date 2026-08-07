from pydantic import BaseModel


class QuizQuestionEmbeddingEntity(BaseModel):
    """Row of the `quiz_question_embeddings` table (see db/init.sql).

    `embedding_3_small` is required (not `| None`), unlike the column's own nullable
    declaration: this entity is only ever constructed for a variant that was actually
    computed (FR-2 — a representation with no input produces no row at all, never a row
    with a null vector), so the write path never legitimately holds one. `id` and
    `created_at` are DB-generated and have no corresponding field, per
    `.claude/rules/code-conventions.md`'s entity rules.
    """

    quiz_question_id: int
    variant: str
    embedding_3_small: list[float]
