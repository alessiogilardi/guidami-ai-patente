"""FR-18: --topic selects which questions are labeled, never how they are judged."""

import inspect

from labeling.services import GoldenSetLabelingService


def test_the_service_accepts_a_topic_filter() -> None:
    parameters = inspect.signature(GoldenSetLabelingService.__init__).parameters

    assert "topics" in parameters


def test_the_topic_filter_is_not_an_epoch_input() -> None:
    """A topic selects *which* questions are labeled, not *how* they are judged (FR-9)."""
    from labeling.mappers import LabelingEpochMapper

    source = inspect.getsource(LabelingEpochMapper)

    assert "topic" not in source, (
        "a topic must never reach labeling_runs: two runs differing only by the "
        "topics they covered are the same configuration epoch"
    )


def test_the_run_entity_has_no_topic_column() -> None:
    from domain.entities.evaluation import LabelingRunEntity

    assert not any("topic" in field for field in LabelingRunEntity.model_fields)
