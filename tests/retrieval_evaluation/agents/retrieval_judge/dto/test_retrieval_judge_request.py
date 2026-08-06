"""Tests for RetrievalJudgeRequest's computed prompt-template fields."""

from domain.models.retrieval import RetrievedComma
from retrieval_evaluation.agents.retrieval_judge.dto import RetrievalJudgeRequest


def _make_comma(
    article_number: str,
    comma_number: str,
    text: str,
    article_title: str = "Segnali di pericolo",
) -> RetrievedComma:
    return RetrievedComma(
        source="cds",
        article_number=article_number,
        article_title=article_title,
        comma_number=comma_number,
        text=text,
        distance=0.05,
    )


def test_correct_answer_it_renders_vero_when_true() -> None:
    request = RetrievalJudgeRequest(
        quiz_text="Domanda.", correct_answer=True, commas=[_make_comma("41", "1", "Testo.")]
    )
    assert request.correct_answer_it == "Vero"


def test_correct_answer_it_renders_falso_when_false() -> None:
    request = RetrievalJudgeRequest(
        quiz_text="Domanda.", correct_answer=False, commas=[_make_comma("41", "1", "Testo.")]
    )
    assert request.correct_answer_it == "Falso"


def test_commas_block_renders_citation_and_article_title_per_comma() -> None:
    request = RetrievalJudgeRequest(
        quiz_text="Domanda.",
        correct_answer=True,
        commas=[
            _make_comma("41", "1", "Primo comma."),
            _make_comma("41", "2", "Secondo comma."),
        ],
    )
    assert request.commas_block == (
        "[cds art. 41 c. 1 — Segnali di pericolo] Primo comma.\n"
        "[cds art. 41 c. 2 — Segnali di pericolo] Secondo comma."
    )


def test_commas_block_uses_each_comma_s_own_article_title() -> None:
    request = RetrievalJudgeRequest(
        quiz_text="Domanda.",
        correct_answer=True,
        commas=[
            _make_comma("41", "1", "Primo comma.", article_title="Segnali di pericolo"),
            _make_comma("142", "8", "Secondo comma.", article_title="Limiti di velocità"),
        ],
    )
    assert request.commas_block == (
        "[cds art. 41 c. 1 — Segnali di pericolo] Primo comma.\n"
        "[cds art. 142 c. 8 — Limiti di velocità] Secondo comma."
    )


def test_commas_block_is_exposed_in_model_dump() -> None:
    request = RetrievalJudgeRequest(
        quiz_text="Domanda.", correct_answer=True, commas=[_make_comma("41", "1", "Testo.")]
    )
    assert "commas_block" in request.model_dump()
