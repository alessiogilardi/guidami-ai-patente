from commons.ai.utils import reciprocal_rank_fusion


def test_item_ranked_first_in_both_lists_wins() -> None:
    rankings = [["a", "b", "c"], ["a", "c", "b"]]

    result = reciprocal_rank_fusion(rankings, k=60)

    assert result[0] == "a"


def test_item_present_in_only_one_ranking_still_scores() -> None:
    rankings = [["a", "b"], ["c"]]

    result = reciprocal_rank_fusion(rankings, k=60)

    assert set(result) == {"a", "b", "c"}


def test_empty_rankings_returns_empty_list() -> None:
    assert reciprocal_rank_fusion([], k=60) == []


def test_ties_broken_by_first_appearance() -> None:
    """Two items scoring identically keep the order in which they first appeared."""
    rankings = [["x", "y"]]

    result = reciprocal_rank_fusion(rankings, k=60)

    assert result == ["x", "y"]
