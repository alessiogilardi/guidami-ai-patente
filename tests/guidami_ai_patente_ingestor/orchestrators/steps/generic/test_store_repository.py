"""Static conformance test: concrete repositories satisfy StoreRepository."""

from typing import TYPE_CHECKING

from guidami_ai_patente_ingestor.orchestrators.steps.generic import StoreRepository

if TYPE_CHECKING:
    from guidami_ai_patente_ingestor.repositories import (
        ArticleCommaStoreRepository,
        ArticleStoreRepository,
        QuizQuestionStoreRepository,
    )


def _conforms(
    art: "ArticleStoreRepository",
    comma: "ArticleCommaStoreRepository",
    qq: "QuizQuestionStoreRepository",
) -> None:
    a: StoreRepository = art  # pyright verifies structural conformance
    b: StoreRepository = comma
    c: StoreRepository = qq
    _ = (a, b, c)


def test_real_repos_satisfy_store_repository_protocol() -> None:
    # Conformance is statically guaranteed by `_conforms` (pyright in CI);
    # here a trivial runtime assertion so the test exists.
    assert _conforms is not None
