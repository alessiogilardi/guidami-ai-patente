"""Resolves what the client can expect from the explanation endpoint."""

from pywire import Autowired, service

from guidami_ai_patente.clients import LabelingStackProvider
from guidami_ai_patente.enums import ExplanationStatus
from guidami_ai_patente.repositories import GoldenSetReadRepository, QuizQuestionRepository


@service
class ExplanationStatusService:
    """Applies FR-4's three cases in order; the first match wins.

    1. A current labeling (FR-8) with supporting commas → `CACHED`, **regardless of
       whether an embedding exists**: the cached path never retrieves, so it never
       needs a query vector.
    2. A current labeling without supporting commas → `UNAVAILABLE`: the judge has
       already answered "the corpus does not justify this", and re-asking under an
       unchanged epoch would produce the same answer at full price.
    3. No current labeling → the embedding decides: present means the live path can
       run (`UNCACHED`), absent means it cannot (`UNAVAILABLE` — FR-7's `not_indexed`).

    The ordering is the substance, not an implementation detail: reversing 1 and 3
    would let a missing embedding downgrade a perfectly good cache hit.
    """

    labeling_stack: Autowired[LabelingStackProvider]
    golden_set: Autowired[GoldenSetReadRepository]
    questions: Autowired[QuizQuestionRepository]

    def resolve(self, number: str) -> ExplanationStatus:
        """Returns the cache state of this question's comma association (FR-4)."""
        labeling = self.golden_set.find_current_labeling(number)
        if labeling is not None:
            return (
                ExplanationStatus.CACHED
                if labeling.has_supporting_commas
                else ExplanationStatus.UNAVAILABLE
            )

        variant = self.labeling_stack.epoch.candidate_variant
        return (
            ExplanationStatus.UNCACHED
            if self.questions.has_embedding(number, variant)
            else ExplanationStatus.UNAVAILABLE
        )
