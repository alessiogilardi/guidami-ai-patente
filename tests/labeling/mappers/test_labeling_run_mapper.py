import pytest
from pydantic import ValidationError

from domain.enums import LabelingRunOrigin
from labeling.mappers import LabelingRunMapper
from labeling.models import LabelingEpoch

_EPOCH = LabelingEpoch(
    judge_model="openrouter/google/gemini-2.5-flash-lite",
    prompt_version="0123456789abcdef",
    candidate_variant="topic_text",
    dense_k=50,
    text_k=50,
    lexeme_fields=("image_description", "text", "topic"),
)


def test_a_batch_run_carries_its_corpus_commit_and_limit() -> None:
    entity = LabelingRunMapper.from_epoch_to_entity(
        _EPOCH,
        LabelingRunOrigin.BATCH,
        shuffle_seed=42,
        corpus_comma_count=29000,
        corpus_commit="deadbeef",
        question_limit=100,
    )

    assert entity.origin is LabelingRunOrigin.BATCH
    assert entity.corpus_commit == "deadbeef"
    assert entity.question_limit == 100


def test_a_live_run_needs_no_corpus_commit() -> None:
    entity = LabelingRunMapper.from_epoch_to_entity(
        _EPOCH, LabelingRunOrigin.LIVE, shuffle_seed=42, corpus_comma_count=29000
    )

    assert entity.corpus_commit is None
    assert entity.question_limit is None


def test_a_batch_run_without_a_corpus_commit_is_refused() -> None:
    with pytest.raises(ValidationError, match="corpus_commit"):
        LabelingRunMapper.from_epoch_to_entity(
            _EPOCH, LabelingRunOrigin.BATCH, shuffle_seed=42, corpus_comma_count=29000
        )


def test_the_entity_carries_every_epoch_field() -> None:
    entity = LabelingRunMapper.from_epoch_to_entity(
        _EPOCH, LabelingRunOrigin.LIVE, shuffle_seed=7, corpus_comma_count=1
    )

    assert (entity.judge_model, entity.prompt_version, entity.candidate_variant) == (
        _EPOCH.judge_model,
        _EPOCH.prompt_version,
        _EPOCH.candidate_variant,
    )
    assert (entity.dense_k, entity.text_k, entity.lexeme_fields) == (
        _EPOCH.dense_k,
        _EPOCH.text_k,
        _EPOCH.lexeme_fields,
    )
