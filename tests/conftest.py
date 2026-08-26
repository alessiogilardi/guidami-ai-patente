"""Shared root fixtures for the test suite."""

import os
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pywire import get_default_container

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente.api.app import create_app
from guidami_ai_patente.configs import AppConfig

_TEST_COMPOSE_FILE = Path(__file__).parent.parent / "docker" / "docker-compose.test.yml"
_TEST_COMPOSE_PROJECT = "guidami-ai-patente-test"
_TEST_POSTGRES_PORT = 5433
_TEST_POSTGRES_DBNAME = "guidami_ai_patente_test"


@pytest.fixture(scope="session", autouse=True)
def _agents_dir_environment() -> Iterator[None]:
    """Pins `AGENTS_DIR` for the whole session (spec 0012, AD-22).

    `LabelingConfig.agents_dir` has no default anywhere, so without this the suite
    would depend on the developer's shell — and a missing value would surface as a
    `ValidationError` from an unrelated test.
    """
    previous = os.environ.get("AGENTS_DIR")
    os.environ["AGENTS_DIR"] = str(Path(__file__).parent.parent / "configs" / "agents")
    yield
    if previous is None:
        del os.environ["AGENTS_DIR"]
    else:
        os.environ["AGENTS_DIR"] = previous


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


@pytest.fixture(scope="session")
def app_config(postgres_test_config: PostgresConnectionConfig) -> AppConfig:
    """The one `AppConfig` the whole pytest session may build (spec 0012 constraint).

    pywire registers it as a process-wide singleton instance, so a second
    construction would either be ignored or raise — either way the suite would stop
    describing the app it actually serves. It points at the ephemeral test stack
    (port 5433), never the dev database (ADR 0011), and at the committed image
    directory FR-12 serves from.
    """
    return AppConfig(
        postgres=postgres_test_config,
        quiz_images_dir=Path(__file__).parent.parent / "data" / "quiz-images",
    )


@pytest.fixture(scope="session")
def api_client(app_config: AppConfig) -> Iterator[TestClient]:
    """A `TestClient` over the single application instance of this session.

    Session-scoped for the same reason `app_config` is: `create_app` registers the
    config on the process-wide container, and a per-test app would re-register it.
    `TestClient` as a context manager runs the app's lifespan, so FR-14's startup
    check executes exactly as it does under uvicorn.
    """
    with TestClient(create_app(app_config)) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def _reset_pywire_container() -> Iterator[None]:
    """Drops pywire's cached singletons at the end of the session.

    `clear_instances()` keeps registrations and releases the built objects — most
    importantly the pooled `PostgresClient` inside `PostgresClientProvider`, whose
    connections would otherwise outlive the session and keep the ephemeral stack's
    teardown waiting.
    """
    yield
    get_default_container().clear_instances()


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
