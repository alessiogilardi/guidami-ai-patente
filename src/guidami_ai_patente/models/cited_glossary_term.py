"""A glossary candidate the vocabulary agent actually cited (FR-1, FR-6, FR-8)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CitedGlossaryTerm(BaseModel):
    """A glossary entry `term_explanation` actually cited (FR-1, FR-8).

    Not `guidami_ai_patente.models.TranslationHint` (spec 0018, `term`/`term_ru` only) —
    that class is the translation UseCase's own input shape, decoupled from the RAG/
    glossary pipeline (spec 0018 AD-1), and has no `definition` concept at all
    (grilling round, 2026-09-23: keeping the two classes separate avoids forcing an
    always-`None` field onto `TranslationHint`'s existing, load-bearing call sites).

    `term`/`term_ru` are consumed by `POST /explanations/translate` to pin the term's
    Russian rendering (spec 0018 FR-8/AD-9, by building a `TranslationHint` from these
    two fields at the forwarding boundary — Task 10); `definition` is read-only local
    render data for the bot's glossary block (FR-8, AD-9) and is never forwarded to the
    translator.
    """

    model_config = ConfigDict(frozen=True)

    term: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1)
    term_ru: str = Field(min_length=1, max_length=80)

    @field_validator("term", "definition", "term_ru")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value
