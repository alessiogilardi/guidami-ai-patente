"""What the explanation path found for a question: commas, an empty verdict, or nothing."""

from pydantic import BaseModel, ConfigDict, model_validator

from .current_labeling import CurrentLabeling
from .labeled_comma import LabeledComma


class CommaSelection(BaseModel):
    """The labeling that applies to a question, and the commas it associated.

    Three states, and the caller reads them by inspecting the two fields:

    * `labeling` set, `commas` non-empty — explainable: render these citations with
      this provenance (FR-5).
    * `labeling` set, `commas` empty — the judge answered that the corpus does not
      justify the question (FR-7).
    * `labeling` `None`, `commas` empty — no query vector exists for the active
      variant, so the live path could not even run: FR-7's `not_indexed`.

    Deliberately carries no `reason`: mapping these facts onto FR-7's vocabulary needs
    the `validated_at`-driven `no_supporting_norm` / `no_supporting_norm_confirmed`
    distinction, which is a presentation choice rather than a retrieval fact, and lives
    in `ExplanationService`.
    """

    model_config = ConfigDict(frozen=True)

    labeling: CurrentLabeling | None
    commas: tuple[LabeledComma, ...] = ()

    @model_validator(mode="after")
    def _require_a_labeling_behind_any_comma(self) -> "CommaSelection":
        """A comma cannot exist without the labeling that associated it."""
        if self.commas and self.labeling is None:
            raise ValueError("commas require the labeling they belong to")
        return self
