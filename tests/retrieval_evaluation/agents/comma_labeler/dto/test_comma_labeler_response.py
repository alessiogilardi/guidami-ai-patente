import pytest
from pydantic import ValidationError

from retrieval_evaluation.agents.comma_labeler.dto import CommaLabelerResponse


def test_accepts_an_empty_number_list_with_a_rationale() -> None:
    response = CommaLabelerResponse(comma_numbers=[], rationale="Nessun comma pertinente.")

    assert response.comma_numbers == []


def test_rejects_more_than_three_numbers() -> None:
    with pytest.raises(ValidationError):
        CommaLabelerResponse(comma_numbers=[1, 2, 3, 4], rationale="Motivazione.")


def test_rejects_a_repeated_number() -> None:
    with pytest.raises(ValidationError, match="must not repeat a candidate number"):
        CommaLabelerResponse(comma_numbers=[2, 2, 3], rationale="Motivazione.")


def test_rejects_an_empty_rationale() -> None:
    with pytest.raises(ValidationError):
        CommaLabelerResponse(comma_numbers=[1], rationale="")
