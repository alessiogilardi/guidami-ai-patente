"""End-to-end container wiring for both entry points (spec 0019 final review, Fix 1).

Every other glossary test bypasses the pywire container via `__new__`
(`GlossaryBuildService.__new__(GlossaryBuildService)`), so none of them exercise the
actual `container.resolve(...)` call `main.py`/`translate_main.py` make. That gap let
a `Provider[AsyncOpenAI]` key mismatch ship: both entry points registered the
OpenRouter provider under its own concrete type (`type(provider)`), while every
glossary agent autowires it as `Provider[AsyncOpenAI]` -- a different key pywire's
exact-key lookup never matched, so `container.resolve(...)` raised
`DependencyResolutionError` before either script did any real work. These tests
register fakes the same way `main()` (build) and `main()` (translate) do, then resolve
the top-level use case each entry point resolves, so a future key mismatch fails here
instead of at runtime.

Registration is done once, in a module-scoped fixture: `pywire.Container.register_instance`
permanently claims its key for the container's lifetime -- `clear_instances()` (used
elsewhere for per-test isolation) only drops the *cached instance*, not the
registration, so registering `GlossaryConfig`/`PostgresClient`/etc. a second time in a
second test would raise `RegistrationError`. Splitting registration (module fixture)
from resolution (one assertion per test) keeps one test per entry point without
double-registering.
"""

import os
from collections.abc import Sequence

import pytest
from openai import AsyncOpenAI
from pydantic_ai.providers import Provider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pywire import get_default_container

from commons.ai.embedding import EmbeddingService
from commons.ai.observability import LlmCallTracker, NullLlmCallTracker
from commons.clients import PostgresClient
from glossary.configs import GlossaryConfig
from glossary.services.glossary_build_service import GlossaryBuildService
from glossary.services.glossary_term_translation_run_service import (
    GlossaryTermTranslationRunService,
)


class _FakePostgresClient:
    """Stands in for `PostgresClient`: never opens a real connection."""


class _FakeEmbeddingService:
    """Stands in for `EmbeddingService`: never calls a real embedding client."""

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


@pytest.fixture(scope="module", autouse=True)
def _register_wiring_fakes() -> None:
    """Registers, once, every instance both `main()`s register before resolving.

    `monkeypatch` is function-scoped, so a module-scoped fixture cannot depend on it;
    `AGENTS_DIR` is set/restored on `os.environ` directly instead, only needing to be
    set before `GlossaryAgentConfigRepository` first reads it (lazily, inside
    `container.resolve(...)` in each test below).
    """
    previous_agents_dir = os.environ.get("AGENTS_DIR")
    os.environ["AGENTS_DIR"] = "configs/agents"
    container = get_default_container()
    config = GlossaryConfig(
        postgres={"host": "localhost", "user": "u", "password": "p", "dbname": "d"}
    )
    container.register_instance(config, as_type=GlossaryConfig)
    container.register_instance(_FakePostgresClient(), as_type=PostgresClient)
    container.register_instance(
        OpenRouterProvider(api_key="test-key-not-a-real-credential"),
        as_type=Provider[AsyncOpenAI],
    )
    container.register_instance(NullLlmCallTracker(), as_type=LlmCallTracker)
    container.register_instance(_FakeEmbeddingService(), as_type=EmbeddingService)
    yield
    container.clear_instances()
    if previous_agents_dir is None:
        os.environ.pop("AGENTS_DIR", None)
    else:
        os.environ["AGENTS_DIR"] = previous_agents_dir


def test_container_resolves_glossary_build_service_end_to_end() -> None:
    """The exact call `main()` makes: `container.resolve(GlossaryBuildService)`.

    This is the test that would have caught the `Provider[AsyncOpenAI]` key mismatch:
    `GlossaryBuildService` -> `GlossaryExtractionService` -> `GlossaryExtractorAgent`,
    whose `provider_dep: Autowired[Provider[AsyncOpenAI]]` field is exactly the key
    the fix in `main.py` had to register the provider under.
    """
    service = get_default_container().resolve(GlossaryBuildService)

    assert isinstance(service, GlossaryBuildService)


def test_container_resolves_glossary_term_translation_run_service_end_to_end() -> None:
    """The exact call `translate_main.main()` makes: `container.resolve(...)`.

    Same coverage as the build-service test above, for `GlossaryTermTranslatorAgent`'s
    identical `provider_dep: Autowired[Provider[AsyncOpenAI]]` field.
    """
    service = get_default_container().resolve(GlossaryTermTranslationRunService)

    assert isinstance(service, GlossaryTermTranslationRunService)
