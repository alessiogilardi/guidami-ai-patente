"""The explanation endpoint's outcome, before it becomes a wire response."""

from pydantic import BaseModel, ConfigDict, model_validator

from guidami_ai_patente.enums import ExplanationResult, InsufficientKnowledgeReason

from .cited_glossary_term import CitedGlossaryTerm
from .current_labeling import CurrentLabeling
from .labeled_comma import LabeledComma


class Explanation(BaseModel):
    """Either a grounded explanation with its citations, or a reasoned refusal.

    The two shapes are mutually exclusive and the validator enforces it, so no caller
    can emit a refusal that also carries prose, or an explanation with no citation —
    the states that would make AD-7's "the explanation is a *rendering* of the
    association, never a second fact" untrue.

    `judge_rationale` passes the judge's stored `rationale` through for transparency
    (AD-6); it is written in evaluation meta-language, so the client decides whether to
    show it. `reason` is the closed vocabulary the client renders wording from.

    `term_explanation`/`translation_hints` are the vocabulary stage's own output (spec
    0020) and are populated independently of `result`/`explanation`/`citations` — an
    insufficient-knowledge refusal can still carry a term explanation (AD-1). They sit
    deliberately outside `_require_a_coherent_shape`, which validates only the legal
    explanation's shape.
    """

    model_config = ConfigDict(frozen=True)

    result: ExplanationResult
    explanation: str | None = None
    citations: tuple[LabeledComma, ...] = ()
    provenance: CurrentLabeling | None = None
    reason: InsufficientKnowledgeReason | None = None
    judge_rationale: str | None = None
    term_explanation: str | None = None
    translation_hints: tuple[CitedGlossaryTerm, ...] = ()

    @model_validator(mode="after")
    def _require_a_coherent_shape(self) -> "Explanation":
        """Rejects a refusal carrying prose, or an explanation citing nothing."""
        if self.result is ExplanationResult.EXPLAINED:
            if self.explanation is None or not self.citations:
                raise ValueError("an explained result needs prose and at least one citation")
            if self.reason is not None:
                raise ValueError("an explained result carries no insufficient-knowledge reason")
        elif self.explanation is not None or self.citations or self.reason is None:
            raise ValueError("an insufficient-knowledge result needs a reason and nothing else")
        return self
