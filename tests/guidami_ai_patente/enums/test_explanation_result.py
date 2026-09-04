"""The explanation endpoint's outcome vocabulary."""

from guidami_ai_patente.enums import ExplanationResult


def test_the_values_are_derived_from_the_names() -> None:
    assert ExplanationResult.EXPLAINED == "explained"
    assert ExplanationResult.INSUFFICIENT_KNOWLEDGE == "insufficient_knowledge"


def test_the_vocabulary_is_closed_to_two_outcomes() -> None:
    """AD-20 rejects a third `temporarily_unavailable` member: an outage is a 503."""
    assert set(ExplanationResult) == {
        ExplanationResult.EXPLAINED,
        ExplanationResult.INSUFFICIENT_KNOWLEDGE,
    }
