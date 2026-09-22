---
paths:
  - "src/guidami_ai_patente/**"
  - "src/guidami_ai_patente_bot/**"
---

# pywire — Spring-style DI

`pywire` (git dependency, see `pyproject.toml`) is a Spring Boot-style IoC container:
`@component`/`@service`/`@repository`/`@client`/`@agent` decorators (all aliases of the
same registration, `pywire/decorators.py`) register a class on the process-wide default
container (`get_default_container()`); fields annotated `Autowired[T]` are populated by
the container after instantiation (`Container._instrument`, `pywire/container.py`). The
container has no FastAPI dependency of its own — only the separate `pywire.fastapi`
integration does — so it works unchanged in a plain script's `main()`: register data
(`register_instance`) and any manually-built `commons` primitives once, `resolve()` the
top-level use case, run it, and (if anything registered a `@pre_destroy` hook)
`container.close()` before exiting.

## Scope

This pattern is the default for the two long-running, request/update-scoped apps in
this repo: the FastAPI app under `src/guidami_ai_patente/` (routers, services,
repositories, mappers, configs) and the Telegram bot under
`src/guidami_ai_patente_bot/` (handlers, services, clients, configs — ADR 0032, which
extended ADR 0015's original FastAPI-only scope).

It also applies to `src/glossary/` (spec 0019's standalone glossary-build package,
2026-09-22): a deliberate, narrow exception to the batch/one-shot default below,
chosen because the package's own agent/service/repository graph benefits from field
injection the same way the API's does, and because it never imports (and is never
imported by) the two batch packages that stay manual — there is no shared-container
collision risk to design around (contrast the bot/API `QuizApiClient` case documented
below). `src/glossary/main.py` is the composition root: it loads `GlossaryConfig`,
builds the few `commons` primitives pywire does not know how to construct
(`PostgresClient`, `EmbeddingService`, the OpenRouter provider) and registers them with
`register_instance`, then `resolve()`s `GlossaryBuildService` and runs it — no
`pywire.fastapi`, no lifespan, just the container's core API.

It does **not** apply to `src/guidami_ai_patente_ingestor/`, `src/labeling/`,
`src/retrieval_evaluation/` or `src/commons/`, which keep manual constructor injection
per [`dependency-injection.md`](./dependency-injection.md) unchanged: **this is a
convention choice already made for those packages, not a technical limitation of
pywire itself** (see the container's FastAPI-independence above) — revisiting it for
any of them is a separate, larger decision, not implied by `glossary` adopting pywire.
Do not "harmonize" one into the other without that decision being made explicitly.

`guidami_ai_patente_bot` uses pywire 0.9.0's `register_async_component`/
`Container.astart()`/`aclose()`/`container.lifespan()` for a component that is itself
an async context manager (needed to `await` a clean `httpx.AsyncClient.aclose()`).
`QuizApiClient` (`src/guidami_ai_patente_bot/clients/quiz_api_client.py`) is the
reference example: `container.lifespan()` wraps the whole async body in `main.py::_run`,
entering the bean via `__aenter__` (which opens the `httpx.AsyncClient`) and exiting it
via `__aexit__` (which closes it). It is registered **explicitly** —
`get_default_container().register_async_component(QuizApiClient)` in `_run`, before
`container.lifespan()` is entered — rather than via the `@async_component` class
decorator, specifically to avoid registering it on the shared default container merely
by being imported: `guidami_ai_patente`'s FastAPI app (`api/app.py`) runs
`FastAPI(lifespan=pywire_lifespan)` against that same default container, and a
decorator-time registration would make its own `astart()` try to enter `QuizApiClient`
too, failing to resolve `BotConfig` (which only the bot's own composition root
registers). ADR 0032 recorded the older, pre-0.9.0 workaround (a hand-called `await
client.aclose()` from `main.py`, with no pywire teardown hook at all) and is now
outdated — it still needs to be superseded to reflect the above.

## Convention — pure field injection, Spring style

- Every service/repository/client/router-dependency class in `src/guidami_ai_patente/`
  is decorated with the role-appropriate pywire decorator (`@service` for
  `services/`, `@repository` for `repositories/`, `@client` for `clients/`, `@component`
  otherwise) — mirrors the `@Service`/`@Repository`/`@Component` split in Spring.
- Dependencies are declared as class-level `Autowired[T]` fields, **always**, with no
  constructor-parameter exception (ADR 0023 — see "Testing with a substitute
  dependency" below):

  ```python
  from pywire import Autowired, service

  from guidami_ai_patente.repositories.dependency_version_repository import (
      DependencyVersionRepository,
  )

  @service
  class HealthCheckService:
      repository: Autowired[DependencyVersionRepository]

      def check(self) -> str:
          return "ok"
  ```

- This intentionally **overrides**, within this package only, the general
  `dependency-injection.md` rule (constructor args, deps last) and the
  `rules/python/architecture.md` "DI over global state" guidance — the pywire default
  container is deliberately the app's composition root, resolved once at startup.
- Do not hand-instantiate a `@service`/`@repository`/`@client` class directly
  (`QuizAnswerChecker()`); resolve it through the container.
- `AppConfig` (`configs/app_config.py`) is data, not a component: it is loaded **once at
  the entry point** (`main.py`, per `rules/python/architecture.md`) and handed to the
  container via `container.register_instance(app_config, as_type=AppConfig)` (ADR 0023,
  superseding ADR 0017's zero-arg-`@component` workaround) — it is not autowired as if it
  were itself a `@component` constructing itself lazily on first resolution.
- Components needing a real constructor argument the container cannot build
  zero-argument (e.g. `PostgresClientProvider` wrapping
  `PostgresClient(config.postgres)`) still build it inside their own `__init__`, after
  their own `Autowired` fields are set (`Container._instrument`'s field-then-`__init__`
  ordering) — ADR 0017's Decision item 2, unaffected by ADR 0023.

### `@provider` — infrastructure implementing an inner-layer contract

A `@provider` is an infrastructure-layer component that implements a contract the
inner layers (a `UseCase`, a `*Service`, the domain) rely on, in order to supply a
technical service or access to an external resource, while those inner layers stay
unaware of the implementation detail behind it. The defining property is the
**direction of the dependency** — infrastructure supplies the inner layers, never the
reverse — **not constructor arity**. An earlier, narrower framing said a provider is
"whatever has a zero-argument `__init__` that performs I/O once"; that framing is
retired. It happened to fit the two examples that existed at the time
(`LabelingStackProvider`, `PostgresClientProvider`), but it was never the actual
defining property, and a class can supply a resource regardless of how its
constructor is shaped.

**The "is this a provider" test**: does the class *decide* something (a business
rule, a branch depending on domain state), or does it only *supply* something (a
resource, a technical capability) for another layer to decide with? A class that
decides stays a `@service`/`UseCase` even if it also "hands back a resource" on the
surface.

**Reference counter-example** — `QuizImageService`
(`src/guidami_ai_patente/services/quiz_image_service.py`): it enforces the FR-12
DB-first authorization ordering (`QuizQuestionRepository.image_is_referenced` before
`QuizImageRepository.read`) before touching the file store. That ordering is a
business rule it decides, so it stays a `@service`, not a `@provider`, despite
superficially "returning an image resource."

**Reference examples**:

- `LabelingStackProvider` (`src/guidami_ai_patente/providers/labeling_stack_provider.py`,
  decorated `@provider`) — loads `comma_labeler.yaml` once via the autowired
  `AgentConfigRepository` and exposes the `LabelingEpoch` derived from it; every
  consumer (the FR-8 precedence query, the FR-14 startup check) reads the same value
  without knowing how it was built.
- `PostgresClientProvider` (`src/guidami_ai_patente/clients/postgres_client_provider.py`)
  — hands the pooled `PostgresClient` to every repository that reads through it, none
  of which knows how the pool was built, which fits the `@provider` definition
  conceptually. It **stays** decorated `@client` and physically in `clients/`: its
  placement there is temporary, pending `commons/` itself adopting pywire, and
  changing its decorator without moving its file would blur the distinction rather
  than sharpen it — the file-move is what marks a class as "the `providers/`
  pattern," not the decorator alone.

**The `@pre_destroy`/teardown shape**: `PostgresClientProvider` has a
`@pre_destroy`-decorated `close` method, which calls `self.client.close()` and
nothing else. This is pywire 0.6.0's bean-teardown mechanism: it is discovered
automatically at registration time regardless of which decorator (`@client`,
`@provider`, ...) the class carries, and run by `Container.close()` in reverse
build order. Since `pywire>=0.7.0`, `Container.close()` is called by
`pywire_lifespan` itself (see "FastAPI wiring" below), not by hand from
`api/app.py::_lifespan`.

### Testing with a substitute dependency

A class needing a mock/double for a unit test stays **field-only** `Autowired[T]` like
every other class here — no constructor-parameter exception. Register the substitute on
the container before resolving the component under test, and call `clear_instances()`
for isolation between tests (`pywire>=0.5.0`; ADR 0023, superseding ADR 0017's Decision
item 3):

```python
from pywire import get_default_container

def test_check_compares_against_the_stored_answer() -> None:
    container = get_default_container()
    container.register_instance(FakeQuizQuestionRepository(), as_type=QuizQuestionRepository)

    checker = container.resolve(QuizAnswerChecker)
    correct, _ = checker(QuizAnswerCheckRequest(number="0001", submitted_answer=True))
    assert correct is True

    container.clear_instances()
```

## FastAPI wiring — `pywire.fastapi.pywire_lifespan`, not manual `Depends()`

Since `pywire>=0.3.0` (`pywire[fastapi]` extra, see `pyproject.toml`), route handlers
declare their dependencies as **bare `Autowired[T]` parameters**, resolved automatically
per request — no manual `Depends(lambda: get_default_container().get(X))` wiring.

The app is wired via `FastAPI(lifespan=pywire_lifespan)` (or a custom lifespan that
nests it). `pywire_lifespan` does two things: bind the container at startup, and call
`Container.close()` at shutdown — which is the only thing in the FastAPI integration
that ever fires a bean's `@pre_destroy`/`on_close` hook.

**`wire(app)` no longer exists.** It was the pre-0.7.0 mechanism, deprecated in 0.7.0
(it only *bound* the container, never tore it down) and **removed outright in
`pywire` 0.8.0** — `from pywire.fastapi import wire` now raises `ImportError`.
`pywire_lifespan` is the single supported entry point. If you need an app that
deliberately does not own its container's lifetime, that is
`pywire_lifespan(close_on_shutdown=False)`, not a resurrected `wire()`.

```python
# api/app.py
from fastapi import FastAPI
from pywire import get_default_container
from pywire.fastapi import pywire_lifespan

from .routers import health


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="guidami-ai-patente API", lifespan=pywire_lifespan)
    get_default_container().register_instance(config, as_type=AppConfig)
    app.include_router(health.router)
    return app
```

`register_instance` (ADR 0023) is what lets `main.py` load `AppConfig` once and hand the
instance to the container, instead of `AppConfig` constructing itself lazily on first
resolution — see `create_app`'s reference implementation for the `RegistrationError`
handling a repeated `create_app(config)` call needs.

```python
# api/routers/health.py
from fastapi import APIRouter
from pywire import Autowired

from guidami_ai_patente.services.health_check_service import HealthCheckService

router = APIRouter(tags=["health"])


@router.get("/health")
async def get_health(service: Autowired[HealthCheckService]) -> HealthResponse:
    return HealthResponse(status=service.check())
```

- **Pass `pywire_lifespan` (bare, or called with `container=`/`close_on_shutdown=`) as
  the app's `lifespan=`, in `api/app.py::create_app`.** Bare
  (`FastAPI(lifespan=pywire_lifespan)`), it binds/closes the module-level default
  container — the same one `@component` writes into. `pywire_lifespan(container=...,
  close_on_shutdown=...)` returns a builder for a non-default container, or for an app
  that shouldn't own the container's lifetime.
- **To compose with app-specific startup/shutdown code** (e.g. `guidami_ai_patente`'s
  own FR-14 judge-coherence diagnostic), nest `pywire_lifespan` on the *outside* of your
  own `@asynccontextmanager`, so your shutdown code runs while beans are still alive —
  its teardown sits in a `finally`, closing the container only after your `yield`
  returns control:

  ```python
  @asynccontextmanager
  async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
      async with pywire_lifespan(app):
          await _run_startup_diagnostics()
          yield

  app = FastAPI(lifespan=_lifespan)
  ```

  See `api/app.py::_lifespan`/`_run_judge_coherence_check` for the reference
  implementation. The diagnostic itself is kept as a standalone top-level function
  precisely so a test can exercise its "resolve() can also raise" guard directly,
  without entering `pywire_lifespan` — that would bind/close the real process-wide
  default container, tearing down beans other tests in the same session may still
  hold.
- **Import order still matters**: `pywire.fastapi` must be imported *before* any router
  module decorates a route with `Autowired[T]`, so the `add_api_route` patch (installed
  at `pywire.fastapi` import time) is in place first — `api/app.py` imports
  `pywire.fastapi` before `from .routers import health` for exactly this reason. The
  patch is installed at `pywire.fastapi`'s own import time, independently of when (or
  whether) the app's container is configured.
- If no container is configured for a given `FastAPI` instance, `Autowired[T]`
  parameters still resolve — silently against the default container — which may not
  have the expected component registered. Always pass `lifespan=pywire_lifespan` in
  `create_app`.
- `TestClient(app)` only runs the lifespan when used as a context manager
  (`with TestClient(app) as client: ...`); without the `with`, a
  `pywire_lifespan`-configured app never binds `app.state.pywire_container`, and
  `Autowired[T]` routes resolve against the default container instead — see
  `tests/conftest.py::api_client` for the reference fixture.
- This supersedes the previous "resolve via `get_default_container().get(...)` at the
  FastAPI wiring boundary" pattern for route handlers specifically; manual
  `container.get(...)` resolution is still the right tool outside of a route handler
  (e.g. a one-off resolution in `main.py`).
