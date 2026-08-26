"""`_lifespan`'s startup diagnostic must never abort the app (FR-14, whole-branch review)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from guidami_ai_patente.api.app import _lifespan


@pytest.mark.asyncio
async def test_a_failing_checker_resolution_does_not_prevent_startup() -> None:
    """Resolving `JudgeCoherenceChecker` can raise before `check()` is ever reached.

    `GoldenSetReadRepository` -> `PostgresClientProvider.__init__` opens a connection
    pool eagerly with `wait=True`, so a container `resolve()` call against a dead
    Postgres port raises `psycopg_pool.PoolTimeout` — outside the try/except that
    lives inside `JudgeCoherenceChecker.check()` itself. `_lifespan` must guard the
    `resolve()` call too, or a database that isn't up yet aborts startup entirely.
    """
    container = MagicMock()
    container.resolve.side_effect = RuntimeError("Postgres is not reachable")

    with patch("guidami_ai_patente.api.app.get_default_container", return_value=container):
        async with _lifespan(FastAPI()):
            pass  # Reaching this point is the assertion: yield was not skipped.
