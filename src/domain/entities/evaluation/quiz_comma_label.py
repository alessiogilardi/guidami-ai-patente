from pydantic import BaseModel, Field, model_validator


class QuizCommaLabelEntity(BaseModel):
    """Row of the `quiz_comma_labels` table (see db/init.sql).

    `labeling_id` is absent by design, unlike every other omitted column here: under
    the single-CTE write of `GoldenSetWriteRepository.insert_labeling`, that column is
    populated from the parent row's generated id inside SQL, so application code never
    supplies it. This is the adjacent case of a *statement-supplied* column, next to
    the usual *DB-generated* ones (`id`/`created_at`) omitted from every entity in this
    project.

    `dense_rank` and `text_rank` are one-based positions of the comma within their
    respective arm's retrieval order (AD-7): `1` means "first result of that arm".
    """

    article_comma_id: int
    judge_rank: int = Field(gt=0)
    dense_rank: int | None = None
    text_rank: int | None = None

    @model_validator(mode="after")
    def _require_at_least_one_arm(self) -> "QuizCommaLabelEntity":
        """Mirrors the table's `quiz_comma_labels_at_least_one_arm` check constraint."""
        if self.dense_rank is None and self.text_rank is None:
            raise ValueError("dense_rank and text_rank cannot both be None")
        return self
