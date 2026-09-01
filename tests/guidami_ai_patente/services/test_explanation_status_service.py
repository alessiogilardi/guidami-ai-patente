"""FR-4's three cases, evaluated in order, first match wins."""

from dataclasses import dataclass, field

from guidami_ai_patente.enums import ExplanationStatus
from guidami_ai_patente.models import CurrentLabeling
from guidami_ai_patente.services import ExplanationStatusService
from labeling.models import LabelingEpoch


@dataclass
class _GoldenSetDouble:
    labeling: CurrentLabeling | None = None

    def find_current_labeling(self, number: str, epoch: LabelingEpoch) -> CurrentLabeling | None:
        return self.labeling


@dataclass
class _QuestionsDouble:
    embedded: bool = False
    probes: list[tuple[str, str]] = field(default_factory=list)

    def has_embedding(self, number: str, variant: str) -> bool:
        self.probes.append((number, variant))
        return self.embedded


@dataclass
class _EpochDouble:
    candidate_variant: str = "topic_text"


@dataclass
class _StackDouble:
    epoch: _EpochDouble = field(default_factory=_EpochDouble)


def _service(
    labeling: CurrentLabeling | None, *, embedded: bool
) -> tuple[ExplanationStatusService, _QuestionsDouble]:
    """Builds the service with doubles bypassing the container.

    `object.__new__` sidesteps pywire's instrumented `__init__` (which would resolve
    the real singletons) — the class has no constructor body of its own, so setting
    the three fields is the whole of its construction.
    """
    questions = _QuestionsDouble(embedded=embedded)
    service = object.__new__(ExplanationStatusService)
    service.questions = questions  # type: ignore[assignment]
    service.golden_set = _GoldenSetDouble(labeling)  # type: ignore[assignment]
    service.labeling_stack = _StackDouble()  # type: ignore[assignment]
    return service, questions


def _labeling(*, has_commas: bool) -> CurrentLabeling:
    return CurrentLabeling(
        id=1,
        rationale="motivazione",
        has_supporting_commas=has_commas,
        origin="batch",
        judge_model="openrouter/google/gemini-2.5-flash-lite",
        human_validated=False,
    )


def test_a_labeling_with_commas_is_cached() -> None:
    service, _ = _service(_labeling(has_commas=True), embedded=False)

    assert service.resolve("0001") is ExplanationStatus.CACHED


def test_a_cache_hit_never_probes_the_embedding() -> None:
    service, questions = _service(_labeling(has_commas=True), embedded=False)

    service.resolve("0001")

    assert questions.probes == [], (
        "FR-4: a cache hit needs no retrieval and therefore no query vector, so the "
        "embedding check is reached only on a miss"
    )


def test_a_labeling_without_commas_is_unavailable() -> None:
    service, _ = _service(_labeling(has_commas=False), embedded=True)

    assert service.resolve("0001") is ExplanationStatus.UNAVAILABLE


def test_no_labeling_but_an_embedding_is_uncached() -> None:
    service, _ = _service(None, embedded=True)

    assert service.resolve("0001") is ExplanationStatus.UNCACHED


def test_no_labeling_and_no_embedding_is_unavailable() -> None:
    service, _ = _service(None, embedded=False)

    assert service.resolve("0001") is ExplanationStatus.UNAVAILABLE


def test_the_probe_uses_the_configured_variant() -> None:
    service, questions = _service(None, embedded=True)

    service.resolve("0042")

    assert questions.probes == [("0042", "topic_text")]
