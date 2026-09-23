"""One glossary_entries row a hybrid retrieval returned (FR-4)."""

from pydantic import BaseModel, ConfigDict


class GlossaryCandidate(BaseModel):
    """A candidate the vocabulary agent may cite, with enough of its row to build a hint.

    `id` is the dedup key across the dense and full-text arms (FR-4).
    """

    model_config = ConfigDict(frozen=True)

    id: int
    source: str
    article_number: str
    comma_number: str
    term: str
    definition: str
    term_ru: str
