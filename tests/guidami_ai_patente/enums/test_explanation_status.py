"""The explanation-status vocabulary is the AD-4 one, not the superseded draft's."""

from guidami_ai_patente.enums import ExplanationStatus, InsufficientKnowledgeReason


def test_the_status_vocabulary_is_exactly_the_three_cache_states() -> None:
    assert {status.value for status in ExplanationStatus} == {
        "cached",
        "uncached",
        "unavailable",
    }


def test_the_superseded_latency_vocabulary_is_gone() -> None:
    values = {status.value for status in ExplanationStatus}

    assert "ready" not in values and "on_demand" not in values, (
        "AD-4 replaced ready|on_demand: a cached explanation still costs a live "
        "writer call, so the field names the cache state, not a latency"
    )


def test_the_reason_vocabulary_separates_a_pipeline_gap_from_a_corpus_gap() -> None:
    assert {reason.value for reason in InsufficientKnowledgeReason} == {
        "no_supporting_norm",
        "no_supporting_norm_confirmed",
        "not_indexed",
    }
