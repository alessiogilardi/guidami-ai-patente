---
paths:
  - "src/guidami_ai_patente/**"
---

# pywire — Spring-style DI, scoped to `src/guidami_ai_patente/` only

`pywire` (git dependency, see `pyproject.toml`) is a Spring Boot-style IoC container:
`@component`/`@service`/`@repository`/`@client`/`@agent` decorators (all aliases of the
same registration, `pywire/decorators.py`) register a class on the process-wide default
container (`get_default_container()`); fields annotated `Autowired[T]` are populated by
the container after instantiation (`Container._instrument`, `pywire/container.py`).

## Scope — does not apply to the ingestion pipeline

This pattern applies **only** to the FastAPI app under `src/guidami_ai_patente/`
(routers, services, repositories, mappers, configs). It does **not** apply to
`src/guidami_ai_patente_ingestor/` or `src/commons/`, which keep manual constructor
injection per [`dependency-injection.md`](./dependency-injection.md) unchanged. The two
packages intentionally use different DI styles — do not "harmonize" one into the other.

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
build order. `api/app.py::_lifespan` calls `Container.close()` from the ASGI
shutdown path, after `yield`.

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

## FastAPI wiring — `pywire.fastapi.wire()`, not manual `Depends()`

Since `pywire>=0.3.0` (`pywire[fastapi]` extra, see `pyproject.toml`), route handlers
declare their dependencies as **bare `Autowired[T]` parameters**, resolved automatically
per request — no manual `Depends(lambda: get_default_container().get(X))` wiring:

```python
# api/app.py
from fastapi import FastAPI
from pywire import get_default_container
from pywire.fastapi import wire

from .routers import health


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="guidami-ai-patente API")
    get_default_container().register_instance(config, as_type=AppConfig)
    wire(app)
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

- **Call `wire(app)` exactly once, in `api/app.py::create_app`, on the `FastAPI` app —
  never on an `APIRouter`.** As of `pywire>=0.3.1`, `wire()` only accepts a `FastAPI`
  instance (passing an `APIRouter` raises `TypeError`); routers do **not** need their
  own `wire()` call. Internally, importing `pywire.fastapi` installs a one-time,
  process-wide patch on `APIRouter.add_api_route` that rewrites bare `Autowired[T]`
  parameters on *every* route, on *any* router, regardless of decoration order —
  resolution itself is deferred to request time, reading `request.app.state.
  pywire_container` (set by `wire(app, container=...)`, defaulting to the module-level
  default container if `wire()` was never called for that app).
- **Import order still matters, but differently than in 0.3.0**: `pywire.fastapi` (i.e.
  `wire`) must be imported *before* any router module decorates a route with
  `Autowired[T]`, so the `add_api_route` patch is installed first — `api/app.py`
  imports `pywire.fastapi` before `from .routers import health` for exactly this
  reason. Calling `wire(app)` itself can happen at any point relative to route
  decoration (before or after `include_router`); only the *import* of `pywire.fastapi`
  needs to precede route decoration.
- If `wire(app, container=...)` is never called for a given `FastAPI` instance,
  `Autowired[T]` parameters still resolve — silently against the default container —
  which may not have the expected component registered. Always call `wire(app)` (or
  `wire(app, container=...)` for a non-default container) in `create_app`.
- This supersedes the previous "resolve via `get_default_container().get(...)` at the
  FastAPI wiring boundary" pattern for route handlers specifically; manual
  `container.get(...)` resolution is still the right tool outside of a route handler
  (e.g. a one-off resolution in `main.py`).
