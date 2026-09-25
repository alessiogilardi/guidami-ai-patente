import types

import pytest
from glossary.services.glossary_term_translation_run_service import (
    GlossaryTermTranslationRunService,
)
from pydantic_ai.exceptions import UnexpectedModelBehavior

from glossary.exceptions import GlossaryTranslationError
from glossary.models import (
    GlossaryTermRow,
    GlossaryTermTranslationRequest,
    TranslatedTerm,
)

_ROWS = [
    GlossaryTermRow(id=1, term="carreggiata", definition="def1"),
    GlossaryTermRow(id=2, term="banchina", definition="def2"),
    GlossaryTermRow(id=3, term="arresto", definition="def3"),
]


class _FakeReadRepository:
    def __init__(self, rows: list[GlossaryTermRow]) -> None:
        self.rows = rows
        self.calls = 0

    def find_missing_translations(self, force: bool) -> list[GlossaryTermRow]:
        self.calls += 1
        return self.rows


class _FakeUpdateRepository:
    def __init__(self) -> None:
        self.updates: list[tuple[int, str]] = []

    def update_many(self, translations) -> None:  # noqa: ANN001
        self.updates.extend(translations)


class _FailingSecondBatchTranslationService:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, rows):  # noqa: ANN001
        self.calls += 1
        if self.calls == 2:
            raise UnexpectedModelBehavior("boom")
        return [TranslatedTerm(term=row.term, term_ru=f"{row.term}-ru") for row in rows]


def _service(config_batch_size, read_repository, update_repository, translation_service):  # noqa: ANN001
    service = GlossaryTermTranslationRunService.__new__(GlossaryTermTranslationRunService)
    service.config = types.SimpleNamespace(translation_batch_size=config_batch_size)  # type: ignore[attr-defined]
    service.read_repository = read_repository  # type: ignore[attr-defined]
    service.update_repository = update_repository  # type: ignore[attr-defined]
    service.translation_service = translation_service  # type: ignore[attr-defined]
    return service


async def test_a_failing_batch_is_skipped_and_the_run_raises_listing_it() -> None:
    read_repository = _FakeReadRepository(_ROWS)
    update_repository = _FakeUpdateRepository()
    translation_service = _FailingSecondBatchTranslationService()
    service = _service(1, read_repository, update_repository, translation_service)

    with pytest.raises(GlossaryTranslationError) as excinfo:
        await service(GlossaryTermTranslationRequest(force=False))

    assert excinfo.value.failed_ids == (2,)
    assert {entry_id for entry_id, _ in update_repository.updates} == {1, 3}


async def test_a_rerun_without_force_only_selects_rows_still_missing() -> None:
    read_repository = _FakeReadRepository([_ROWS[0]])
    update_repository = _FakeUpdateRepository()

    async def _translate(rows):  # noqa: ANN001
        return [TranslatedTerm(term=r.term, term_ru=f"{r.term}-ru") for r in rows]

    service = _service(10, read_repository, update_repository, _translate)
    await service(GlossaryTermTranslationRequest(force=False))

    assert read_repository.calls >= 1
