"""Input of the per-question labeling unit shared by the batch and the API."""

from collections.abc import Callable
from dataclasses import dataclass

from domain.models.retrieval import QuizEvaluationRow


# A `dataclass` rather than a Pydantic `BaseModel` for the reason the convention names
# explicitly (`.claude/rules/code-conventions.md`): it holds a **callable** field, which
# a `BaseModel` cannot type without `arbitrary_types_allowed=True` — and that would
# switch off the validation the model was chosen for.
@dataclass(frozen=True)
class QuestionLabelingRequest:
    """One question to label, plus a lazy handle on the run that will own the labeling.

    Attributes:
        row: The question with its query vector, as read by either caller.
        resolve_run_id: Returns the `labeling_runs.id` the labeling belongs to, called
            **once the judge has answered** and never before. The batch passes a
            closure over an id it already inserted; the API passes the lazy
            create-or-reuse of its live run (FR-9), so a failed judge leaves no run row
            behind — FR-13's "no row is written to any golden-set table" (AD-20).
    """

    row: QuizEvaluationRow
    resolve_run_id: Callable[[], int]
