"""Shared root fixtures for the test suite."""

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import SecretStr

from commons.configs import PostgresConnectionConfig

_TEST_COMPOSE_FILE = Path(__file__).parent.parent / "docker" / "docker-compose.test.yml"
_TEST_COMPOSE_PROJECT = "guidami-ai-patente-test"
_TEST_POSTGRES_PORT = 5433
_TEST_POSTGRES_DBNAME = "guidami_ai_patente_test"


@pytest.fixture(scope="session")
def _postgres_test_stack() -> Iterator[None]:
    """Starts the ephemeral, isolated Postgres test stack for the pytest session.

    Runs in its own container on its own port (docker/docker-compose.test.yml,
    tmpfs data directory), entirely separate from the dev stack started via
    `docker compose up` in `docker/docker-compose.yml`. Only started when at
    least one collected test requests `postgres_test_config` (directly or via a
    module fixture built on top of it); torn down at the end of the session.
    """
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(_TEST_COMPOSE_FILE),
            "-p",
            _TEST_COMPOSE_PROJECT,
            "up",
            "-d",
            "--wait",
        ],
        check=True,
    )
    yield
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(_TEST_COMPOSE_FILE),
            "-p",
            _TEST_COMPOSE_PROJECT,
            "down",
            "-v",
        ],
        check=True,
    )


@pytest.fixture(scope="session")
def postgres_test_config(_postgres_test_stack: None) -> PostgresConnectionConfig:
    """Connection config for the isolated test Postgres stack — never the dev database.

    Requesting this fixture starts the ephemeral test stack for the session.
    """
    config = PostgresConnectionConfig(
        host="localhost",
        port=_TEST_POSTGRES_PORT,
        user="guidami",
        password=SecretStr("guidami"),
        dbname=_TEST_POSTGRES_DBNAME,
    )
    assert config.port != 5432, (
        "integration tests must target the isolated test Postgres stack "
        "(docker-compose.test.yml), never the dev database"
    )
    return config


@dataclass
class RecordingProgressReporter:
    """Test double for `ProgressReporter` recording every call in order.

    Each method appends `(method_name, args)` to `calls`, in the exact order and
    arity the corresponding protocol method receives them. `count` is a convenience
    for asserting how many times a given method fired, without slicing `calls`
    by hand in every test.
    """

    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def begin_run(self, total_flows: int) -> None:
        self.calls.append(("begin_run", (total_flows,)))

    def begin_flow(self, name: str) -> None:
        self.calls.append(("begin_flow", (name,)))

    def end_flow(self) -> None:
        self.calls.append(("end_flow", ()))

    def begin_step(self, name: str, index: int, total: int) -> None:
        self.calls.append(("begin_step", (name, index, total)))

    def end_step(self) -> None:
        self.calls.append(("end_step", ()))

    def begin_items(self, label: str, total: int) -> None:
        self.calls.append(("begin_items", (label, total)))

    def advance_item(self) -> None:
        self.calls.append(("advance_item", ()))

    def end_items(self) -> None:
        self.calls.append(("end_items", ()))

    def count(self, method: str) -> int:
        """Returns how many times `method` was called."""
        return sum(1 for name, _ in self.calls if name == method)


@pytest.fixture
def progress_recorder() -> RecordingProgressReporter:
    """A fresh `RecordingProgressReporter`, one per test."""
    return RecordingProgressReporter()
