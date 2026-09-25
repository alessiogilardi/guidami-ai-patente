"""Tests for GlossaryTermOrigin (FR-8)."""

from guidami_ai_patente.enums import GlossaryTermOrigin


def test_members_have_auto_derived_string_values() -> None:
    assert GlossaryTermOrigin.VERBATIM_CORPUS == "verbatim_corpus"
    assert GlossaryTermOrigin.AGENT_GENERATED == "agent_generated"
