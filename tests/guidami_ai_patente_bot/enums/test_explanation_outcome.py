"""ExplanationOutcome's values must match the API's wire strings exactly (FR-2)."""

from guidami_ai_patente_bot.enums import ExplanationOutcome


def test_the_members_match_the_apis_wire_strings() -> None:
    assert ExplanationOutcome.EXPLAINED == "explained"
    assert ExplanationOutcome.INSUFFICIENT_KNOWLEDGE == "insufficient_knowledge"
