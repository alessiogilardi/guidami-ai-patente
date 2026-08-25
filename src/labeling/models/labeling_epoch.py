from pydantic import BaseModel, ConfigDict, model_validator

from domain.validators import require_canonical_lexeme_fields


class LabelingEpoch(BaseModel):
    """The six inputs that identify one judge configuration (spec 0012, AD-8).

    Exactly the columns of `uq_labeling_runs_live_config`, in the same order. Two
    labelings produced under equal epochs are interchangeable; under different epochs
    they are not, which is what lets a model or prompt change invalidate the cache
    without a single `DELETE`.

    `lexeme_fields` is held in canonical (sorted) form: it is compared as a whole
    array by FR-8's precedence query, and array comparison is order-sensitive, so a
    cosmetic reordering of the configured list must not open a new epoch. The
    validator makes that structural rather than conventional —
    `LabelingEpochMapper` is the only sanctioned constructor.
    """

    model_config = ConfigDict(frozen=True)

    judge_model: str
    prompt_version: str
    candidate_variant: str
    dense_k: int
    text_k: int
    lexeme_fields: tuple[str, ...]

    @model_validator(mode="after")
    def _require_canonical_lexeme_fields(self) -> "LabelingEpoch":
        """Rejects an empty or unsorted `lexeme_fields`.

        Shares its implementation with `LabelingRunEntity` (D8/D13) — `domain/` owns
        the check, `labeling/` imports it, so the two never drift apart.
        """
        require_canonical_lexeme_fields(self.lexeme_fields)
        return self
