import types

import psycopg
import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from glossary.exceptions import GlossaryDefinitionSimplificationError
from glossary.models import (
    GlossaryDefinitionRow,
    GlossaryDefinitionSimplificationRequest,
    SimplifiedDefinition,
)
from glossary.services.glossary_definition_simplification_run_service import (
    GlossaryDefinitionSimplificationRunService,
)

_ROWS = [
    GlossaryDefinitionRow(id=1, term="carreggiata", definition="def1"),
    GlossaryDefinitionRow(id=2, term="banchina", definition="def2"),
    GlossaryDefinitionRow(id=3, term="arresto", definition="def3"),
]


class _FakeReadRepository:
    def __init__(self, rows: list[GlossaryDefinitionRow]) -> None:
        self.rows = rows
        self.calls = 0

    def find_missing_simplifications(self, force: bool) -> list[GlossaryDefinitionRow]:
        self.calls += 1
        return self.rows


class _FakeUpdateRepository:
    def __init__(self) -> None:
        self.updates: list[tuple[int, str]] = []

    def update_many(self, simplifications) -> None:  # noqa: ANN001
        self.updates.extend(simplifications)


class _FailingSecondBatchSimplificationService:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, rows):  # noqa: ANN001
        self.calls += 1
        if self.calls == 2:
            raise UnexpectedModelBehavior("boom")
        return [
            SimplifiedDefinition(term=row.term, definition_plain=f"{row.term}-plain")
            for row in rows
        ]


class _FailingSecondBatchUpdateRepository:
    def __init__(self) -> None:
        self.calls = 0
        self.updates: list[tuple[int, str]] = []

    def update_many(self, simplifications) -> None:  # noqa: ANN001
        self.calls += 1
        if self.calls == 2:
            raise psycopg.Error("boom")
        self.updates.extend(simplifications)


def _service(config_batch_size, read_repository, update_repository, simplification_service):  # noqa: ANN001
    service = GlossaryDefinitionSimplificationRunService.__new__(
        GlossaryDefinitionSimplificationRunService
    )
    service.config = types.SimpleNamespace(simplification_batch_size=config_batch_size)  # type: ignore[attr-defined]
    service.read_repository = read_repository  # type: ignore[attr-defined]
    service.update_repository = update_repository  # type: ignore[attr-defined]
    service.simplification_service = simplification_service  # type: ignore[attr-defined]
    return service


async def test_a_failing_batch_is_skipped_and_the_run_raises_listing_it() -> None:
    read_repository = _FakeReadRepository(_ROWS)
    update_repository = _FakeUpdateRepository()
    simplification_service = _FailingSecondBatchSimplificationService()
    service = _service(1, read_repository, update_repository, simplification_service)

    with pytest.raises(GlossaryDefinitionSimplificationError) as excinfo:
        await service(GlossaryDefinitionSimplificationRequest(force=False))

    assert excinfo.value.failed_ids == (2,)
    assert {entry_id for entry_id, _ in update_repository.updates} == {1, 3}


async def test_a_failing_write_is_isolated_to_its_own_batch_and_the_run_raises() -> None:
    read_repository = _FakeReadRepository(_ROWS)
    update_repository = _FailingSecondBatchUpdateRepository()

    async def _simplify(rows):  # noqa: ANN001
        return [
            SimplifiedDefinition(term=r.term, definition_plain=f"{r.term}-plain") for r in rows
        ]

    service = _service(1, read_repository, update_repository, _simplify)

    with pytest.raises(GlossaryDefinitionSimplificationError) as excinfo:
        await service(GlossaryDefinitionSimplificationRequest(force=False))

    assert excinfo.value.failed_ids == (2,)
    assert {entry_id for entry_id, _ in update_repository.updates} == {1, 3}


async def test_a_rerun_without_force_only_selects_rows_still_missing() -> None:
    read_repository = _FakeReadRepository([_ROWS[0]])
    update_repository = _FakeUpdateRepository()

    async def _simplify(rows):  # noqa: ANN001
        return [
            SimplifiedDefinition(term=r.term, definition_plain=f"{r.term}-plain") for r in rows
        ]

    service = _service(10, read_repository, update_repository, _simplify)
    await service(GlossaryDefinitionSimplificationRequest(force=False))

    assert read_repository.calls >= 1
