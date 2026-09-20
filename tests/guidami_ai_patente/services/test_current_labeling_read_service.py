"""FR-5's read-only half: serve a current labeling, or say there isn't one (AD-3, AD-4)."""

from dataclasses import dataclass, field

import pytest

from guidami_ai_patente.exceptions import LabelingNotReadyError
from guidami_ai_patente.models import CurrentLabeling, LabeledComma
from guidami_ai_patente.services import CurrentLabelingReadService
from labeling.models import LabelingEpoch

_EPOCH = LabelingEpoch(
    judge_model="openrouter/google/gemini-2.5-flash-lite",
    prompt_version="0123456789abcdef",
    candidate_variant="topic_text",
    dense_k=50,
    text_k=50,
    lexeme_fields=("image_description", "text", "topic"),
)


def _labeling(*, has_commas: bool) -> CurrentLabeling:
    return CurrentLabeling(
        id=7,
        rationale="motivazione del giudice",
        has_supporting_commas=has_commas,
        origin="live",
        judge_model=_EPOCH.judge_model,
        human_validated=False,
    )


def _comma(judge_rank: int) -> LabeledComma:
    return LabeledComma(
        source="cds",
        article_number="157",
        article_title="Sosta",
        comma_number=str(judge_rank),
        text="Testo.",
        judge_rank=judge_rank,
    )


@dataclass
class _GoldenSetDouble:
    labeling: CurrentLabeling | None = None
    commas: list[LabeledComma] = field(default_factory=list)
    comma_reads: list[int] = field(default_factory=list)

    def find_current_labeling(self, number: str, epoch: LabelingEpoch) -> CurrentLabeling | None:
        return self.labeling

    def find_labeled_commas(self, labeling_id: int) -> list[LabeledComma]:
        self.comma_reads.append(labeling_id)
        return list(self.commas)


@dataclass
class _QuestionsDouble:
    embedded: bool = False

    def has_embedding(self, number: str, variant: str) -> bool:
        return self.embedded


@dataclass
class _IdentityDouble:
    epoch: LabelingEpoch = _EPOCH


def _service(
    golden_set: _GoldenSetDouble, questions: _QuestionsDouble
) -> CurrentLabelingReadService:
    """Builds the service with doubles, bypassing the container.

    `object.__new__` sidesteps pywire's instrumented `__init__`; the class has no
    constructor body, so assigning the three fields is the whole of its
    construction (same pattern as `test_comma_selector_service.py`).
    """
    service = object.__new__(CurrentLabelingReadService)
    service.judge_identity = _IdentityDouble()  # type: ignore[assignment]
    service.golden_set = golden_set  # type: ignore[assignment]
    service.questions = questions  # type: ignore[assignment]
    return service


@pytest.mark.asyncio
async def test_a_current_labeling_with_commas_is_returned() -> None:
    golden_set = _GoldenSetDouble(labeling=_labeling(has_commas=True), commas=[_comma(1)])

    selection = await _service(golden_set, _QuestionsDouble())("0001")

    assert selection.labeling is not None
    assert [comma.judge_rank for comma in selection.commas] == [1]


@pytest.mark.asyncio
async def test_an_empty_verdict_returns_the_labeling_with_no_commas() -> None:
    golden_set = _GoldenSetDouble(labeling=_labeling(has_commas=False))

    selection = await _service(golden_set, _QuestionsDouble())("0001")

    assert selection.labeling is not None
    assert selection.commas == ()
    assert golden_set.comma_reads == [], "no child read when the flag says there are none"


@pytest.mark.asyncio
async def test_a_cascaded_away_child_set_reads_as_no_commas() -> None:
    """AD-10's detection hole (spec 0011 lineage): the flag says true, the rows are gone."""
    golden_set = _GoldenSetDouble(labeling=_labeling(has_commas=True), commas=[])

    selection = await _service(golden_set, _QuestionsDouble())("0001")

    assert selection.commas == ()
    assert golden_set.comma_reads == [7]


@pytest.mark.asyncio
async def test_no_labeling_and_no_embedding_is_reported_as_not_indexed() -> None:
    """FR-7's not_indexed, unchanged behavior (spec 0017, AD-4)."""
    selection = await _service(_GoldenSetDouble(), _QuestionsDouble(embedded=False))("0001")

    assert selection.labeling is None
    assert selection.commas == ()


@pytest.mark.asyncio
async def test_no_labeling_with_an_embedding_is_not_ready_yet() -> None:
    """AD-4: a contract violation — the caller should have called POST /label first."""
    with pytest.raises(LabelingNotReadyError):
        await _service(_GoldenSetDouble(), _QuestionsDouble(embedded=True))("0001")
