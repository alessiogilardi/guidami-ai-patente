from pydantic import BaseModel, model_validator

from domain.enums import LabelingRunOrigin
from domain.validators import require_canonical_lexeme_fields


class LabelingRunEntity(BaseModel):
    """Row of the `labeling_runs` table (see db/init.sql).

    `id` and `created_at` are DB-generated and have no corresponding field here.
    Records the run provenance a labeling pass is reconstructible from: judge model,
    prompt version, candidate variant, both arm depths, the lexeme fields, the shuffle
    seed, the corpus commit and comma count, the requested question limit, and whether
    the run is a batch pass or a live API epoch (spec 0012, AD-8).

    `lexeme_fields` is stored in its canonical form — sorted — because
    `labeling_runs.lexeme_fields` is compared as a whole array by FR-8's precedence
    query, and array comparison is order-sensitive. Canonicalisation happens in
    `LabelingEpochMapper`; the validator here is the enforcement, so no other write
    path can open a spurious epoch by reordering a YAML list.
    """

    judge_model: str
    prompt_version: str
    candidate_variant: str
    dense_k: int
    text_k: int
    lexeme_fields: tuple[str, ...]
    shuffle_seed: int
    corpus_commit: str | None = None
    corpus_comma_count: int
    question_limit: int | None = None
    origin: LabelingRunOrigin = LabelingRunOrigin.BATCH

    @model_validator(mode="after")
    def _require_canonical_lexeme_fields(self) -> "LabelingRunEntity":
        """Rejects an empty or unsorted `lexeme_fields` (spec 0012, AD-8).

        The enforcement backstop, not a redundant check: `LabelingEpochMapper` is the
        sanctioned constructor and canonicalises there, but this entity is reachable
        without going through it, and `labeling_runs.lexeme_fields` is compared as a
        whole array by FR-8's precedence query. Shares its implementation with
        `LabelingEpoch` (D8/D13) — `domain/` owns it, `labeling/` imports it.
        """
        require_canonical_lexeme_fields(self.lexeme_fields)
        return self

    @model_validator(mode="after")
    def _require_corpus_commit_on_a_batch_run(self) -> "LabelingRunEntity":
        """Mirrors the `labeling_runs_batch_has_corpus_commit` check constraint."""
        if self.origin is LabelingRunOrigin.BATCH and self.corpus_commit is None:
            raise ValueError("corpus_commit is required on a batch run")
        return self
