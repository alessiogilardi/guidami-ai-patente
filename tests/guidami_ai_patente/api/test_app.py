"""`_run_judge_coherence_check` must never abort startup (FR-14, whole-branch review)."""

from unittest.mock import MagicMock, patch

import pytest

from guidami_ai_patente.api.app import _run_judge_coherence_check


@pytest.mark.asyncio
async def test_a_failing_checker_resolution_does_not_prevent_startup() -> None:
    """Resolving `JudgeCoherenceChecker` can raise before `check()` is ever reached.

    `GoldenSetReadRepository` -> `PostgresClientProvider.__init__` opens a connection
    pool eagerly with `wait=True`, so a container `resolve()` call against a dead
    Postgres port raises `psycopg_pool.PoolTimeout` — outside the try/except that
    lives inside `JudgeCoherenceChecker.check()` itself. `_run_judge_coherence_check`
    must guard the `resolve()` call too, or a database that isn't up yet aborts
    startup entirely.

    Exercises the function directly rather than through `_lifespan`/`pywire_lifespan`:
    entering those would bind and, at exit, close the real process-wide default
    container, tearing down beans other tests in the same session may still hold.
    """
    container = MagicMock()
    container.resolve.side_effect = RuntimeError("Postgres is not reachable")

    with patch("guidami_ai_patente.api.app.get_default_container", return_value=container):
        await _run_judge_coherence_check()  # Not raising is the assertion.
