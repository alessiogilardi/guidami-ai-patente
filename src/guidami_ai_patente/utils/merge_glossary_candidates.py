"""Merges DB-retrieved and on-demand glossary candidates (FR-6, AD-6)."""

from collections.abc import Sequence

from guidami_ai_patente.enums import GlossaryTermOrigin
from guidami_ai_patente.models import GlossaryCandidate


def merge_glossary_candidates(
    db_candidates: Sequence[GlossaryCandidate], on_demand_entries: Sequence[tuple[str, str]]
) -> list[GlossaryCandidate]:
    """Merges the two glossary candidate sources, DB-retrieved winning on conflict.

    Every `db_candidates` entry is kept as-is (already `origin=VERBATIM_CORPUS`, the
    model's default). Each `(term, definition)` on-demand pair becomes a
    `GlossaryCandidate` with `origin=AGENT_GENERATED`, unless its normalized term
    (`term.strip().casefold()`) already matches a DB candidate's — the DB entry,
    extracted verbatim from the corpus, wins (FR-6). Two on-demand entries sharing a
    normalized term are both kept: the agent should not produce this, but nothing here
    enforces it — the pre-existing `ExplanationService._deduplicated_hints` dedup
    (same key) still applies downstream once the writer agent decides what to cite.

    An on-demand candidate is built with `term_ru=None` (an on-demand entry is always
    Italian-only) and `definition_plain` left at its field default (`None`) — the
    `definition_plain or definition` fallback downstream then simply resolves to the
    on-demand agent's own `definition`, exactly like any other not-yet-simplified row.

    Args:
        db_candidates: Candidates from `GlossaryReadRepository.candidates_for`.
        on_demand_entries: `(term, definition)` pairs from `GlossaryEnricherAgent`.

    Returns:
        Every `db_candidates` entry, plus each non-conflicting `on_demand_entries` pair.
    """
    db_terms = {candidate.term.strip().casefold() for candidate in db_candidates}
    merged = list(db_candidates)
    for term, definition in on_demand_entries:
        if term.strip().casefold() not in db_terms:
            merged.append(
                GlossaryCandidate(
                    term=term,
                    definition=definition,
                    term_ru=None,
                    origin=GlossaryTermOrigin.AGENT_GENERATED,
                )
            )
    return merged
