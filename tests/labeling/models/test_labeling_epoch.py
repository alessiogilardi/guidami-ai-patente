import pytest
from pydantic import ValidationError

from labeling.models import LabelingEpoch


def _epoch(**overrides: object) -> LabelingEpoch:
    fields: dict[str, object] = {
        "judge_model": "openrouter/google/gemini-2.5-flash-lite",
        "prompt_version": "0123456789abcdef",
        "candidate_variant": "topic_text",
        "dense_k": 50,
        "text_k": 50,
        "lexeme_fields": ("image_description", "text", "topic"),
    }
    fields.update(overrides)
    return LabelingEpoch(**fields)  # type: ignore[arg-type]


def test_a_canonical_epoch_is_accepted() -> None:
    assert _epoch().lexeme_fields == ("image_description", "text", "topic")


def test_unsorted_lexeme_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="sorted"):
        _epoch(lexeme_fields=("topic", "text", "image_description"))


def test_two_epochs_differing_only_in_dense_k_are_not_equal() -> None:
    assert _epoch() != _epoch(dense_k=10)
