"""A glossary candidate the vocabulary agent actually cited (FR-1, FR-6, FR-8)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from guidami_ai_patente.enums import GlossaryTermOrigin


class CitedGlossaryTerm(BaseModel):
    """A glossary entry `term_explanation` actually cited (FR-1, FR-8).

    Not `guidami_ai_patente.models.TranslationHint` (spec 0018, `term`/`term_ru` only) —
    that class is the translation UseCase's own input shape, decoupled from the RAG/
    glossary pipeline (spec 0018 AD-1), and has no `definition` concept at all.

    `term`/`term_ru` are consumed by `POST /explanations/translate` to pin the term's
    Russian rendering (spec 0018 FR-8/AD-9); `definition` is read-only local render data
    for the bot's glossary block and is never forwarded to the translator. `term_ru` may
    be `None`: a term can legitimately have no Russian rendering yet, or (spec 0021)
    never will, when `origin` is `AGENT_GENERATED`. `origin` has no default — it is
    always resolved explicitly from the `GlossaryCandidate` it was built from (FR-8).
    """

    model_config = ConfigDict(frozen=True)

    term: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1)
    term_ru: str | None = Field(default=None, max_length=80)
    origin: GlossaryTermOrigin

    @field_validator("term", "definition")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("term_ru")
    @classmethod
    def _reject_blank_term_ru(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value
