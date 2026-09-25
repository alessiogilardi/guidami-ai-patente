"""Tests for merge_glossary_candidates (FR-6, AD-6)."""

from guidami_ai_patente.utils import merge_glossary_candidates

from guidami_ai_patente.enums import GlossaryTermOrigin
from guidami_ai_patente.models import GlossaryCandidate


def test_an_empty_on_demand_list_returns_the_db_list_unchanged() -> None:
    db_candidates = [GlossaryCandidate(term="carreggiata", definition="...", term_ru="x")]

    merged = merge_glossary_candidates(db_candidates, [])

    assert merged == db_candidates


def test_a_non_conflicting_on_demand_entry_is_kept_as_agent_generated() -> None:
    merged = merge_glossary_candidates([], [("revoca", "Definizione live.")])

    assert len(merged) == 1
    assert merged[0].term == "revoca"
    assert merged[0].definition == "Definizione live."
    assert merged[0].origin is GlossaryTermOrigin.AGENT_GENERATED
    assert merged[0].term_ru is None
    assert merged[0].definition_plain is None


def test_a_conflicting_on_demand_entry_is_dropped_and_the_db_one_wins() -> None:
    db_candidate = GlossaryCandidate(term="sospensione", definition="Definizione DB.", term_ru="x")

    merged = merge_glossary_candidates([db_candidate], [("sospensione", "Definizione live.")])

    assert merged == [db_candidate]


def test_a_case_and_whitespace_variant_still_conflicts() -> None:
    """AD-6: term.strip().casefold() is the dedup key, not bare casefold()."""
    db_candidate = GlossaryCandidate(term="Sospensione", definition="Definizione DB.", term_ru="x")

    merged = merge_glossary_candidates([db_candidate], [(" sospensione ", "Definizione live.")])

    assert merged == [db_candidate]


def test_two_on_demand_entries_sharing_a_term_are_both_kept() -> None:
    """The agent should not produce this, but the merge function does not enforce it."""
    merged = merge_glossary_candidates(
        [], [("revoca", "Definizione A."), ("revoca", "Definizione B.")]
    )

    assert len(merged) == 2
