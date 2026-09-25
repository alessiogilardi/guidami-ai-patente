"""Tests for GlossaryCandidate's narrowed shape (AD-8)."""

from guidami_ai_patente.models import GlossaryCandidate


def test_the_model_is_narrowed_to_its_five_real_fields() -> None:
    """AD-8: id/source/article_number/comma_number are read nowhere outside the repository."""
    assert set(GlossaryCandidate.model_fields.keys()) == {
        "term",
        "definition",
        "definition_plain",
        "term_ru",
        "origin",
    }
