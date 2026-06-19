"""Test di conformità statica: i repository concreti soddisfano StoreRepository."""

from typing import TYPE_CHECKING

from guidami_ai_patente_ingestor.orchestrators.steps.generic import StoreRepository

if TYPE_CHECKING:
    from guidami_ai_patente_ingestor.repositories import (
        KnowledgeChunkStoreRepository,
        QuizQuestionStoreRepository,
    )


def _conforms(
    kc: "KnowledgeChunkStoreRepository",
    qq: "QuizQuestionStoreRepository",
) -> None:
    a: StoreRepository = kc  # pyright verifica la conformità strutturale
    b: StoreRepository = qq
    _ = (a, b)


def test_real_repos_satisfy_store_repository_protocol() -> None:
    # La conformità è garantita staticamente da `_conforms` (pyright in CI);
    # qui un'asserzione runtime banale per far esistere il test.
    assert _conforms is not None
