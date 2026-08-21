import pytest
from pydantic import ValidationError

from domain.entities.evaluation import QuizCommaLabelEntity


def test_rejects_a_label_with_neither_arm_rank() -> None:
    with pytest.raises(ValidationError, match="dense_rank and text_rank cannot both be None"):
        QuizCommaLabelEntity(article_comma_id=2, judge_rank=1, dense_rank=None, text_rank=None)


def test_accepts_a_label_with_only_one_arm_rank() -> None:
    dense_only = QuizCommaLabelEntity(
        article_comma_id=2, judge_rank=1, dense_rank=3, text_rank=None
    )
    text_only = QuizCommaLabelEntity(
        article_comma_id=2, judge_rank=1, dense_rank=None, text_rank=7
    )

    assert dense_only.dense_rank == 3
    assert dense_only.text_rank is None
    assert text_only.dense_rank is None
    assert text_only.text_rank == 7


def test_rejects_a_non_positive_judge_rank() -> None:
    with pytest.raises(ValidationError):
        QuizCommaLabelEntity(article_comma_id=2, judge_rank=0, dense_rank=1, text_rank=None)
