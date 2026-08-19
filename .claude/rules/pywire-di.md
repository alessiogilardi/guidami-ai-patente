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
- Dependencies are declared as class-level `Autowired[T]` fields, **not** as constructor
  parameters:

  ```python
  from pywire import Autowired, service

  @service
  class QuizAnswerChecker:
      repository: Autowired[QuizQuestionRepository]

      def check(self, question_id: int, answer: str) -> bool:
          question = self.repository.get(question_id)
          return question.correct_answer == answer
  ```

- This intentionally **overrides**, within this package only, the general
  `dependency-injection.md` rule (constructor args, deps last) and the
  `rules/python/architecture.md` "DI over global state" guidance — the pywire default
  container is deliberately the app's composition root, resolved once at startup.
- Do not hand-instantiate a `@service`/`@repository`/`@client` class directly
  (`QuizAnswerChecker()`); resolve it through the container.
- `AppConfig` (`configs/app_config.py`) is data, not a component: it is loaded once at
  the entry point (`main.py`, per `rules/python/architecture.md`) and, if a component
  needs it, exposed to the container as a registered instance/provider — it is not
  autowired as if it were itself a `@component`.

## FastAPI wiring — `pywire.fastapi.wire()`, not manual `Depends()`

Since `pywire>=0.3.0` (`pywire[fastapi]` extra, see `pyproject.toml`), route handlers
declare their dependencies as **bare `Autowired[T]` parameters**, resolved automatically
per request — no manual `Depends(lambda: get_default_container().get(X))` wiring:

```python
# api/app.py
from fastapi import FastAPI
from pywire.fastapi import wire

from .routers import health


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="guidami-ai-patente API")
    wire(app)
    app.include_router(health.router)
    return app
```

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
