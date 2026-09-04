import pytest
from pydantic import ValidationError

from domain.entities.evaluation import LabelingRunEntity
from domain.enums import LabelingRunOrigin


def _entity(**overrides: object) -> LabelingRunEntity:
    fields: dict[str, object] = {
        "judge_model": "openrouter/google/gemini-2.5-flash-lite",
        "prompt_version": "0123456789abcdef",
        "candidate_variant": "topic_text",
        "dense_k": 50,
        "text_k": 50,
        "lexeme_fields": ("image_description", "text", "topic"),
        "shuffle_seed": 42,
        "corpus_commit": "deadbeef",
        "corpus_comma_count": 29000,
    }
    fields.update(overrides)
    return LabelingRunEntity(**fields)  # type: ignore[arg-type]


def test_origin_defaults_to_batch() -> None:
    assert _entity().origin is LabelingRunOrigin.BATCH


def test_a_live_run_may_omit_the_corpus_commit() -> None:
    entity = _entity(origin=LabelingRunOrigin.LIVE, corpus_commit=None)

    assert entity.corpus_commit is None


def test_a_batch_run_without_a_corpus_commit_is_rejected() -> None:
    with pytest.raises(ValidationError, match="corpus_commit"):
        _entity(corpus_commit=None)


def test_unsorted_lexeme_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="sorted"):
        _entity(lexeme_fields=("topic", "text"))


def test_empty_lexeme_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        _entity(lexeme_fields=())
