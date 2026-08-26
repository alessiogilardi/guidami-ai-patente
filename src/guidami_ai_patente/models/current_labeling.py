"""The labeling FR-8's precedence rule selects for a question."""

from pydantic import BaseModel, ConfigDict


class CurrentLabeling(BaseModel):
    """The one labeling that counts for a question, per FR-8.

    Produced by the precedence query, which already applies the whole rule in SQL: a
    human-validated labeling wins over any other, otherwise the most recent one whose
    run matches the active configuration epoch. Absence of a row means "no current
    labeling", which is a cache miss — never an error.

    `origin` and `judge_model` are carried for the provenance block plan 3's
    explanation response returns; `has_supporting_commas` is what FR-4 branches on.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    rationale: str
    has_supporting_commas: bool
    origin: str
    judge_model: str
    human_validated: bool
