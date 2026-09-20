"""spec 0017 AD-10: /label's own deadline and 404 check around CommaSelectorService."""

import asyncio
from dataclasses import dataclass, field

import pytest

from guidami_ai_patente.exceptions import ExplanationUnavailableError, QuestionNotFoundError
from guidami_ai_patente.models import CommaSelection, CurrentLabeling
from guidami_ai_patente.services import LabelingService


@dataclass
class _SelectorDouble:
    selection: CommaSelection = field(default_factory=lambda: CommaSelection(labeling=None))
    delay: float = 0.0
    calls: list[str] = field(default_factory=list)

    async def __call__(self, number: str) -> CommaSelection:
        self.calls.append(number)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.selection


@dataclass
class _QuestionsDouble:
    exists: bool = True

    def find_correct_answer(self, number: str) -> bool | None:
        return True if self.exists else None


@dataclass
class _ConfigDouble:
    labeling_deadline_s: float = 5.0


def _service(
    selector: _SelectorDouble,
    config: _ConfigDouble | None = None,
    questions: _QuestionsDouble | None = None,
) -> LabelingService:
    service = object.__new__(LabelingService)
    service.config = config or _ConfigDouble()  # type: ignore[assignment]
    service.questions = questions or _QuestionsDouble()  # type: ignore[assignment]
    service.selector = selector  # type: ignore[assignment]
    return service


def _labeling() -> CurrentLabeling:
    return CurrentLabeling(
        id=1,
        rationale="motivazione",
        has_supporting_commas=True,
        origin="batch",
        judge_model="openrouter/google/gemini-2.5-flash-lite",
        human_validated=False,
    )


@pytest.mark.asyncio
async def test_a_cache_hit_is_served_within_the_deadline() -> None:
    selector = _SelectorDouble(selection=CommaSelection(labeling=_labeling()))

    selection = await _service(selector)("0001")

    assert selection.labeling is not None
    assert selector.calls == ["0001"]


@pytest.mark.asyncio
async def test_exceeding_the_deadline_becomes_a_503() -> None:
    """Spec 0017 AD-10: a timeout is an outage, never a statement about the law."""
    selector = _SelectorDouble(delay=1)

    with pytest.raises(ExplanationUnavailableError):
        await _service(selector, _ConfigDouble(labeling_deadline_s=0.01))("0001")


@pytest.mark.asyncio
async def test_an_unknown_number_is_a_404() -> None:
    """Consistency with /check and /explanation, both of which also 404."""
    selector = _SelectorDouble()

    with pytest.raises(QuestionNotFoundError):
        await _service(selector, questions=_QuestionsDouble(exists=False))("9999")

    assert selector.calls == [], "the selector must not run for a question that does not exist"
