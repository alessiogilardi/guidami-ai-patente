from unittest.mock import MagicMock

from commons.repositories.db import CorpusReadRepository
from domain.models.retrieval import QuizEvaluationRow, RetrievedComma
from retrieval_evaluation.services import CandidateSetService


class _StubLexemeService:
    """Local stand-in for `QuestionLexemeService`, avoiding a dependency on it."""

    def __init__(self, lexemes: list[str]) -> None:
        self._lexemes = lexemes

    def build(self, row: QuizEvaluationRow) -> list[str]:
        return self._lexemes


def _make_row() -> QuizEvaluationRow:
    return QuizEvaluationRow(
        id=1,
        number="1",
        topic="Segnaletica",
        text="Il segnale indica obbligo di fermata.",
        correct_answer=True,
        exact_keywords=None,
        image_filename=None,
        image_description=None,
        embedding=[0.1, 0.2],
    )


def _make_comma(comma_id: int) -> RetrievedComma:
    return RetrievedComma(
        id=comma_id,
        source="cds",
        article_number="41",
        article_title="Segnali di pericolo",
        comma_number="1",
        text=f"Testo del comma {comma_id}.",
        distance=0.1,
    )


def _make_corpus_repository(dense_ids: list[int], text_ids: list[int]) -> MagicMock:
    repository = MagicMock(spec=CorpusReadRepository)
    repository.dense_top_k.return_value = [_make_comma(i) for i in dense_ids]
    repository.text_match_top_k.return_value = [_make_comma(i) for i in text_ids]
    return repository


def test_union_contains_every_comma_of_both_arms_exactly_once() -> None:
    corpus_repository = _make_corpus_repository([1, 2, 3], [3, 4])
    service = CandidateSetService(
        dense_k=50,
        text_k=50,
        corpus_repository=corpus_repository,
        lexeme_service=_StubLexemeService(["'x'"]),
    )

    candidates = service.build(_make_row())

    assert {candidate.comma.id for candidate in candidates} == {1, 2, 3, 4}
    assert len(candidates) == 4


def test_a_comma_found_by_both_arms_carries_both_ranks() -> None:
    corpus_repository = _make_corpus_repository([1, 2, 3], [3, 4])
    service = CandidateSetService(
        dense_k=50,
        text_k=50,
        corpus_repository=corpus_repository,
        lexeme_service=_StubLexemeService(["'x'"]),
    )

    candidates = service.build(_make_row())

    both_arms = next(candidate for candidate in candidates if candidate.comma.id == 3)
    assert both_arms.dense_rank == 3
    assert both_arms.text_rank == 1


def test_a_single_arm_comma_leaves_the_other_rank_null() -> None:
    corpus_repository = _make_corpus_repository([1, 2, 3], [3, 4])
    service = CandidateSetService(
        dense_k=50,
        text_k=50,
        corpus_repository=corpus_repository,
        lexeme_service=_StubLexemeService(["'x'"]),
    )

    candidates = service.build(_make_row())
    by_id = {candidate.comma.id: candidate for candidate in candidates}

    assert by_id[1].dense_rank == 1
    assert by_id[1].text_rank is None
    assert by_id[4].text_rank == 2
    assert by_id[4].dense_rank is None


def test_a_short_arm_does_not_raise() -> None:
    corpus_repository = _make_corpus_repository([1], [])
    service = CandidateSetService(
        dense_k=50,
        text_k=50,
        corpus_repository=corpus_repository,
        lexeme_service=_StubLexemeService(["'x'"]),
    )

    candidates = service.build(_make_row())

    assert len(candidates) == 1
    assert candidates[0].comma.id == 1


def test_the_union_is_not_truncated_to_either_depth() -> None:
    corpus_repository = _make_corpus_repository([1, 2], [3, 4])
    service = CandidateSetService(
        dense_k=2,
        text_k=2,
        corpus_repository=corpus_repository,
        lexeme_service=_StubLexemeService(["'x'"]),
    )

    candidates = service.build(_make_row())

    assert len(candidates) == 4


def test_the_arm_depths_are_taken_from_configuration() -> None:
    corpus_repository = _make_corpus_repository([1], [2])
    service = CandidateSetService(
        dense_k=7,
        text_k=11,
        corpus_repository=corpus_repository,
        lexeme_service=_StubLexemeService(["'x'"]),
    )

    service.build(_make_row())

    corpus_repository.dense_top_k.assert_called_once()
    assert corpus_repository.dense_top_k.call_args.args[1] == 7
    corpus_repository.text_match_top_k.assert_called_once()
    assert corpus_repository.text_match_top_k.call_args.args[1] == 11


def test_an_empty_lexeme_list_skips_the_text_arm() -> None:
    corpus_repository = _make_corpus_repository([1, 2], [])
    service = CandidateSetService(
        dense_k=50,
        text_k=50,
        corpus_repository=corpus_repository,
        lexeme_service=_StubLexemeService([]),
    )

    candidates = service.build(_make_row())

    corpus_repository.text_match_top_k.assert_not_called()
    assert {candidate.comma.id for candidate in candidates} == {1, 2}


def test_two_builds_of_the_same_question_give_the_same_set() -> None:
    corpus_repository = _make_corpus_repository([1, 2, 3], [3, 4])
    service = CandidateSetService(
        dense_k=50,
        text_k=50,
        corpus_repository=corpus_repository,
        lexeme_service=_StubLexemeService(["'x'"]),
    )
    row = _make_row()

    first = service.build(row)
    second = service.build(row)

    first_view = [(c.comma.id, c.dense_rank, c.text_rank) for c in first]
    second_view = [(c.comma.id, c.dense_rank, c.text_rank) for c in second]
    assert first_view == second_view
