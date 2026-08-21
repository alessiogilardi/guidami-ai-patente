"""Tests for CommaLabelerRequest's computed prompt-template fields."""

from domain.models.retrieval import RetrievedComma
from retrieval_evaluation.agents.comma_labeler.dto import CommaLabelerRequest


def _make_comma(
    article_number: str,
    comma_number: str,
    text: str,
    article_title: str = "Segnali di pericolo",
    comma_id: int = 1,
    distance: float = 0.1,
) -> RetrievedComma:
    return RetrievedComma(
        id=comma_id,
        source="cds",
        article_number=article_number,
        article_title=article_title,
        comma_number=comma_number,
        text=text,
        distance=distance,
    )


def test_candidates_block_numbers_each_candidate_from_one() -> None:
    request = CommaLabelerRequest(
        quiz_text="Domanda.",
        correct_answer=True,
        candidates=[
            _make_comma("41", "1", "Primo comma.", comma_id=1),
            _make_comma("41", "2", "Secondo comma.", comma_id=2),
            _make_comma("41", "3", "Terzo comma.", comma_id=3),
        ],
    )
    lines = request.candidates_block.splitlines()

    assert len(lines) == 3
    assert lines[0].startswith("1.")
    assert "cds art. 41 c. 1" in lines[0]
    assert lines[1].startswith("2.")
    assert "cds art. 41 c. 2" in lines[1]
    assert lines[2].startswith("3.")
    assert "cds art. 41 c. 3" in lines[2]


def test_candidates_block_leaks_no_score_or_arm() -> None:
    request = CommaLabelerRequest(
        quiz_text="Domanda.",
        correct_answer=True,
        candidates=[
            _make_comma("41", "1", "Primo comma.", comma_id=1, distance=0.1234),
            _make_comma("41", "2", "Secondo comma.", comma_id=2, distance=0.9876),
        ],
    )
    rendered = request.candidates_block

    assert "0.1234" not in rendered
    assert "0.9876" not in rendered
    assert "dense" not in rendered
    assert "text_rank" not in rendered
    assert "distance" not in rendered
    assert "score" not in rendered
