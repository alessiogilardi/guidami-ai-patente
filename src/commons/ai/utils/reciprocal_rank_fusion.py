"""Reciprocal Rank Fusion: fuses several ranked lists into one, by identity alone."""

from collections.abc import Hashable, Sequence


def reciprocal_rank_fusion[T: Hashable](rankings: Sequence[Sequence[T]], k: int) -> list[T]:
    """Fuses `rankings` (each already ordered best-first) into one ranking.

    Each item's fused score is `sum(1 / (k + rank) for each ranking it appears in)`,
    `rank` 1-indexed within that ranking; an item missing from a ranking contributes 0
    for that ranking, not a penalty. Ties broken by first appearance across `rankings`
    (stable). Domain-agnostic: `T` is whatever identity the caller's rankings share (e.g.
    a citation string) — this function knows nothing about quiz questions or corpus
    commas, so a later hybrid (dense+FTS) fusion feature can reuse it unchanged (AD-3).
    """
    scores: dict[T, float] = {}
    first_seen: dict[T, int] = {}
    order = 0
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            if item not in first_seen:
                first_seen[item] = order
                order += 1
    return sorted(scores, key=lambda item: (-scores[item], first_seen[item]))
