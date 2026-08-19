# ADR 0016: Adopt pywire's native FastAPI wiring, pin the dependency by release tag

## Status

Proposed

## Context

ADR 0015 adopted `pywire` for Spring-style dependency injection in
`src/guidami_ai_patente/`, but at the time only `GET /health` existed and it
had no dependencies to resolve — the FastAPI-boundary wiring pattern
described in `.claude/rules/pywire-di.md` (resolve via
`get_default_container().get(X)`, typically behind a manual
`Depends(...)`) was never actually exercised against a real route.

`pywire` (previously pinned: 0.2.1, floating on the git default branch with
no tag/rev in `[tool.uv.sources]`) shipped a first-party FastAPI
integration, `pywire.fastapi.wire()`, in 0.3.0, rewriting bare
`Autowired[T]` route parameters into `Depends(...)` under the hood so route
handlers no longer need to write that boilerplate by hand. 0.3.0's `wire()`
worked by setting `route_class` on its target's router at call time, which
made it order-sensitive and per-`APIRouter`: wiring the main `FastAPI` app
did not propagate to routers mounted onto it via `include_router(...)`, and
each router had to be wired individually, before any route was decorated
on it — verified empirically: reversing the order (wiring only the app,
decorating an unwired router) raised `fastapi.exceptions.FastAPIError` at
import time, not just a silent resolution failure. `pywire` 0.3.1 redesigned
`wire()` to fix exactly this: it now only accepts the `FastAPI` app,
installs a one-time process-wide patch on `APIRouter.add_api_route` so
decoration order stops mattering, and defers the actual container lookup
to request time via `request.app.state.pywire_container`.

## Decision

1. Bump `pywire` 0.2.1 -> 0.3.1 and pin `[tool.uv.sources]` to
   `tag = "v0.3.1"` instead of floating on the default branch — the
   package now has tagged releases, so pinning a tag gives a reproducible,
   auditable upgrade path (`uv lock --upgrade-package pywire` becomes an
   explicit, reviewable version bump) instead of silently picking up
   whatever `main` contains at `uv lock` time.
2. Add the `pywire[fastapi]` extra to the `pywire` dependency spec in
   `[project.dependencies]` (`fastapi` itself was already a direct
   dependency at a version satisfying the extra's `>=0.110` floor).
3. Use `pywire.fastapi.wire()` for every FastAPI route in
   `src/guidami_ai_patente/` going forward, declaring dependencies as bare
   `Autowired[T]` route parameters instead of hand-writing
   `Depends(lambda: get_default_container().get(X))`. Call `wire(app)`
   exactly once, in `api/app.py::create_app`, on the `FastAPI` app itself —
   never on an `APIRouter` (0.3.1's `wire()` raises `TypeError` if passed
   one). Import `pywire.fastapi` before importing any router module, so
   its process-wide `add_api_route` patch is installed before a router
   decorates a route with `Autowired[T]`; the `wire(app)` call itself may
   happen at any point relative to route decoration or `include_router`.
   Full convention in `.claude/rules/pywire-di.md`.
4. Prove the integration against a real dependency chain, not just a
   trivial no-arg component: `GET /health` resolves
   `services/health_check_service.py::HealthCheckService`
   (`repository: Autowired[DependencyVersionRepository]`) as a bare
   `Autowired[HealthCheckService]` parameter, and the response includes
   the installed `pywire` version (read via
   `importlib.metadata.version("pywire")` in
   `repositories/dependency_version_repository.py::DependencyVersionRepository`)
   — both to exercise nested field injection through a live FastAPI
   request and to give a runtime signal that the upgrade actually took
   effect. Verified two ways: `tests/guidami_ai_patente/api/routers/
   test_health.py` (FastAPI `TestClient`, asserting `status == "ok"` only —
   asserting the exact `pywire_version` string was tried and dropped, since
   it turns every future `pywire` bump into an unrelated test failure) and
   a real `uv run api` process hit with an actual HTTP request.

## Alternatives considered

- **Keep floating `[tool.uv.sources]` on the default branch**: matches
  `flowstep`'s `branch = "main"` pin, but `flowstep` pins the branch
  explicitly while `pywire` had no pin at all; now that `pywire` cuts
  tagged releases, floating (implicitly or via `branch = "main"`) gives
  up reproducibility for no benefit — a tag pin was strictly better here.
- **Keep the manual `Depends(lambda: get_default_container().get(X))`
  pattern from `.claude/rules/pywire-di.md`**: still works and needed no
  upgrade, but every route handler would repeat the same boilerplate
  `pywire.fastapi.wire()` now generates automatically; the whole point of
  adopting a Spring-style container in ADR 0015 was to remove this kind
  of manual resolution ceremony at call sites.
- **Wire each `APIRouter` individually (0.3.0's only working pattern)**:
  abandoned once 0.3.1 shipped `wire(app)`-only semantics — one call site
  in `create_app` is simpler than one per router module and removes the
  decoration-order footgun entirely, at the cost of depending on a very
  recent (0.3.1) release.

## Consequences

- Route handlers in `src/guidami_ai_patente/` declare dependencies purely
  through type annotations (`Autowired[T]`), consistent with the
  field-injection style ADR 0015 already established for services and
  repositories — one fewer DI idiom to keep track of inside the same
  package.
- Exactly one `wire(app)` call, in `create_app`, wires every router
  mounted on the app — no per-router call to remember, but `api/app.py`
  must keep importing `pywire.fastapi` before its router modules, or a
  route decorated with `Autowired[T]` before the patch installs would
  behave like a plain (unresolved) FastAPI parameter.
- If `wire(app, container=...)` is ever omitted for a given app instance,
  `Autowired[T]` parameters still resolve, but silently against the
  default container — a wrong-container bug that fails to raise; called
  out explicitly in `.claude/rules/pywire-di.md` as a review point.
- Tag-pinning `pywire` means future upstream fixes/features require an
  explicit `uv lock --upgrade-package pywire` plus a tag bump in
  `pyproject.toml`, rather than arriving automatically on the next
  `uv lock` — a deliberate trade of automatic pickup for reproducibility.
