"""Input of the vocabulary explainer: the question and its glossary candidates (FR-2)."""

from pydantic import BaseModel, Field, computed_field

from guidami_ai_patente.models import GlossaryCandidate

_NO_IMAGE_DESCRIPTION = "Nessuna immagine allegata a questa domanda."


class QuestionExplainerRequest(BaseModel):
    """Everything the vocabulary agent may speak about, and nothing else (FR-2, AD-4).

    Deliberately has no field derived from the answer — `correct_answer`,
    `rule_explanation`, `core_concepts`, `topic` do not exist here, structurally, not by
    omission convention (a test asserts this).

    Attributes:
        text: The quiz question's own text, verbatim.
        image_description: Description of the attached image, when present.
        candidates: Glossary candidates from `GlossaryReadRepository`, already shuffled
            by the caller (`ExplanationService`, Task 7) before construction — order
            carries no relevance signal here, mirroring `comma_labeler.yaml`'s judge
            prompt, which never claims presentation order means anything either
            (grilling round, 2026-09-23: `GlossaryReadRepository` itself stays
            RRF-ordered and deterministic; the shuffle is `ExplanationService`'s job).
            May be empty (FR-4).
    """

    text: str = Field(min_length=1)
    image_description: str | None = None
    candidates: list[GlossaryCandidate] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def image_description_it(self) -> str:
        """Renders the image description, or the Italian absent-image fallback."""
        return self.image_description or _NO_IMAGE_DESCRIPTION

    @computed_field  # type: ignore[prop-decorator]
    @property
    def candidates_block(self) -> str:
        """Renders the candidates as one numbered `[term] definition` line.

        Numbering starts at 1, matching the ordinals
        `QuestionExplainerResponse.cited_term_numbers` must reference.
        """
        return "\n".join(
            f"{index}. [{candidate.term}] {candidate.definition}"
            for index, candidate in enumerate(self.candidates, start=1)
        )
