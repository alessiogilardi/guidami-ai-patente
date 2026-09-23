"""Tests for bot-side explanation models."""

from guidami_ai_patente_bot.models.cited_glossary_term import CitedGlossaryTerm
from guidami_ai_patente_bot.models.quiz_explanation import QuizExplanation


def test_quiz_explanation_carries_term_explanation_and_hints() -> None:
    """Test that QuizExplanation accepts and carries term_explanation and translation_hints."""
    explanation = QuizExplanation.model_validate(
        {
            "status": "explained",
            "explanation": "...",
            "term_explanation": "La domanda chiede...",
            "translation_hints": [{"term": "x", "definition": "y", "term_ru": "z"}],
        }
    )
    assert explanation.term_explanation == "La domanda chiede..."
    assert explanation.translation_hints == (
        CitedGlossaryTerm(term="x", definition="y", term_ru="z"),
    )
