"""The explanation UseCase's input: which question, and what the user answered."""

from pydantic import BaseModel, ConfigDict


class ExplanationRequest(BaseModel):
    """A question to explain, optionally with the answer the user submitted (FR-11).

    Two arguments, so a request DTO rather than a bare `str`
    (`.claude/rules/use-case-invocation.md`).

    `submitted` is an input to the **writer only** (AD-21): it does not enter the cache
    key, does not affect FR-8's precedence, and is never persisted. Optional so a review
    flow ("go over yesterday's mistakes") can ask for an explanation without replaying
    an answer.
    """

    model_config = ConfigDict(frozen=True)

    number: str
    submitted: bool | None = None
