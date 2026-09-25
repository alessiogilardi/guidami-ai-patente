"""One glossary_entries row a hybrid retrieval returned (FR-4)."""

from pydantic import BaseModel, ConfigDict


class GlossaryCandidate(BaseModel):
    """A candidate the vocabulary agent may cite, with enough of its row to build a hint.

    `id` is the dedup key across the dense and full-text arms (FR-4). `definition_plain`
    is `None` until `simplify-glossary-definitions` (spec 0022) reaches this row —
    `ExplanationService._deduplicated_hints` falls back to the verbatim `definition`
    when it is `None`.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    source: str
    article_number: str
    comma_number: str
    term: str
    definition: str
    definition_plain: str | None = None
    term_ru: str | None
