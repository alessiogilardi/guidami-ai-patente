"""A candidate the vocabulary agent may cite (FR-4, FR-6, FR-8)."""

from pydantic import BaseModel, ConfigDict

from guidami_ai_patente.enums import GlossaryTermOrigin


class GlossaryCandidate(BaseModel):
    """A candidate the vocabulary agent may cite, with enough of its row to build a hint.

    Narrowed to the fields the vocabulary pipeline actually reads (AD-8, spec 0021): a
    repo-wide search confirmed `id`/`source`/`article_number`/`comma_number` are read
    nowhere outside `GlossaryReadRepository` itself — the dense/full-text fusion these
    fields exist for happens entirely in SQL, before `_row_to_candidate` ever builds a
    `GlossaryCandidate`. `origin` says *who produced* the candidate (FR-8);
    `definition_plain` says *which register* its definition is in (spec 0022) and is
    `None` until `simplify-glossary-definitions` reaches this row, or always for an
    `AGENT_GENERATED` candidate (`ExplanationService._deduplicated_hints` falls back to
    the verbatim `definition` in either case).
    """

    model_config = ConfigDict(frozen=True)

    term: str
    definition: str
    definition_plain: str | None = None
    term_ru: str | None
    origin: GlossaryTermOrigin = GlossaryTermOrigin.VERBATIM_CORPUS
