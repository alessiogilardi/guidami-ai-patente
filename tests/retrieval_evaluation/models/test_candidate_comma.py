import pytest
from pydantic import ValidationError

from domain.models.retrieval import RetrievedComma
from retrieval_evaluation.models import CandidateComma


def _make_comma(comma_id: int = 1) -> RetrievedComma:
    return RetrievedComma(
        id=comma_id,
        source="cds",
        article_number="41",
        article_title="Segnali di pericolo",
        comma_number="1",
        text="Testo del comma.",
        distance=0.1,
    )


def test_rejects_a_candidate_from_neither_arm() -> None:
    with pytest.raises(ValidationError, match="a candidate must come from at least one arm"):
        CandidateComma(comma=_make_comma(), dense_rank=None, text_rank=None)
