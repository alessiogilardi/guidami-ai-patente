"""AD-1: `term_explanation`/`translation_hints` sit outside the coherent-shape validator."""

from guidami_ai_patente.enums import ExplanationResult, InsufficientKnowledgeReason
from guidami_ai_patente.models import CitedGlossaryTerm, Explanation


def test_term_explanation_and_hints_sit_outside_the_coherent_shape_validator() -> None:
    """AD-1: populated independently of `result`.

    An insufficient-knowledge result can still carry a term_explanation.
    """
    explanation = Explanation(
        result=ExplanationResult.INSUFFICIENT_KNOWLEDGE,
        reason=InsufficientKnowledgeReason.NOT_INDEXED,
        term_explanation="La domanda chiede se...",
        translation_hints=(CitedGlossaryTerm(term="x", definition="y", term_ru="z"),),
    )
    assert explanation.term_explanation is not None
