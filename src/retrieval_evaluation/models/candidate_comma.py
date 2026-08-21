from pydantic import BaseModel, model_validator

from domain.models.retrieval import RetrievedComma


class CandidateComma(BaseModel):
    """One candidate comma of the two-arm union, with the rank each arm gave it.

    `dense_rank`/`text_rank` are one-based positions within their arm's retrieval
    order (AD-7): `1` means "first result of that arm", `None` means the arm did not
    retrieve this comma at all.
    """

    comma: RetrievedComma
    dense_rank: int | None = None
    text_rank: int | None = None

    @model_validator(mode="after")
    def _require_at_least_one_arm(self) -> "CandidateComma":
        """A candidate must come from at least one arm to exist in the union."""
        if self.dense_rank is None and self.text_rank is None:
            raise ValueError("a candidate must come from at least one arm")
        return self
