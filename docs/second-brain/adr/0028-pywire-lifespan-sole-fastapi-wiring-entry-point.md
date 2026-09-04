# ADR 0028: `pywire_lifespan` is the sole FastAPI wiring entry point, after `wire()`'s removal in pywire 0.8.0

## Status

Accepted

## Context

ADR 0016 adopted `pywire`'s native FastAPI integration and made
`pywire.fastapi.wire(app)`, called exactly once in `api/app.py::create_app`, the
mechanism that associates a container with the app (its Decision item 3).

`wire()` only *bound* the container — it never closed it — so no bean's teardown hook
ever ran when the service stopped. `pywire` 0.7.0 introduced `pywire_lifespan`, which
binds at startup **and** calls `Container.close()` at shutdown, and deprecated `wire()`
in documentation only. This repo migrated on 2026-09-01, in the same change that gave
`PostgresClientProvider` a `@pre_destroy` hook (spec 0013, FR-6): `api/app.py::_lifespan`
nests `async with pywire_lifespan(app)` around the FR-14 judge-coherence diagnostic.

`pywire` 0.8.0 then **removed `wire()` outright** — it is the release's sole breaking
change. `from pywire.fastapi import wire` now raises `ImportError`, and `pywire.fastapi`
exports only `pywire_lifespan` (plus its private helpers). ADR 0016's Decision item 3 and
two of its Consequences therefore describe an API that no longer exists, while the rest of
that ADR (tag-pinning the dependency, the `pywire[fastapi]` extra, proving the integration
against a real dependency chain on `GET /health`) is unaffected and still holds.

The bump `v0.7.0 -> v0.8.0` was verified before this ADR was written: 810 tests passed,
`uv run pytest -m integration` green, `ruff check`/`ruff format --check` clean, `pyright`
0 errors — no code change was required beyond the `pyproject.toml` tag, because no
`wire()` call existed anywhere in `src/` or `tests/`.

## Decision

1. **`pywire_lifespan` is the only supported way to configure a container on a
   `FastAPI` app in this repository.** `api/app.py::create_app` passes
   `lifespan=_lifespan`, and `_lifespan` nests `async with pywire_lifespan(app)` on the
   outside of the app's own startup code, so app-level shutdown runs while beans are
   still alive and `Container.close()` fires last (its teardown sits in a `finally`).
2. **ADR 0016's Decision item 3 is superseded by item 1 above**; ADR 0016's items 1, 2
   and 4 remain in force. ADR 0016 is marked `Superseded by ADR 0028` rather than
   rewritten, per the incremental-amendment precedent this repo already follows
   (0017 amends 0015, 0023 supersedes 0017, 0027 supersedes 0024).
3. **Pin `pywire` at `tag = "v0.8.0"`** in `[tool.uv.sources]`, continuing ADR 0016's
   item 1 tag-pinning policy.
4. **Two operational invariants carry over from `wire()` and must not be lost**, both
   restated in `.claude/rules/pywire-di.md`:
   - `pywire.fastapi` must still be imported **before** any router module decorates a
     route with `Autowired[T]` — the `add_api_route` patch is installed at
     `pywire.fastapi`'s own import time, independently of when the container is
     configured. `api/app.py` imports it above its router imports for this reason.
   - A `FastAPI` app whose container is never configured still resolves `Autowired[T]`
     route parameters — **silently**, against the module-level default container. The
     failure mode ADR 0016 flagged for a forgotten `wire(app)` is unchanged for a
     forgotten `lifespan=`.
5. **Tests must drive a `pywire_lifespan`-configured app as a context manager.**
   `TestClient(app)` used without `with` never runs the lifespan, so
   `app.state.pywire_container` is never bound and every `Autowired[T]` route silently
   falls back to the default container. `tests/conftest.py::api_client` is the reference
   fixture. This is a new hazard `wire()` did not have (it bound eagerly at call time),
   and it is the one real cost of the migration.

## Alternatives considered

- **Stay on `v0.7.0` and keep `wire()` available as a fallback**: costs nothing today,
  but pins the project to a release whose successor already exists purely to preserve an
  API this repo does not call. It would also leave `.claude/rules/pywire-di.md`
  documenting two wiring mechanisms when only one is used, which is exactly the kind of
  drift that made ADR 0016's item 3 go stale unnoticed.
- **Amend ADR 0016 in place rather than superseding it**: fewer files, but it would
  erase the record of why `wire(app)` was chosen in the first place (0.3.0's
  order-sensitive, per-`APIRouter` design and the empirical `FastAPIError` that motivated
  0.3.1) — context that is still the reason the import-order invariant in item 4 exists.
- **Vendor or re-implement `wire()` locally** to avoid the lifespan-in-tests hazard:
  re-adds a mechanism upstream deliberately removed, and forfeits the teardown that is
  the whole reason `PostgresClientProvider`'s pool is now closed deterministically
  (spec 0013, FR-6).

## Consequences

- Container lifetime is tied to the app's lifetime: every resolved bean's
  `@pre_destroy`/`on_close` runs on shutdown, in reverse build order. This is what makes
  the pooled `PostgresClient` — and, once Phase 3 lands, the `LlmCallTrackerProvider`'s
  background queue — release deterministically instead of at process death.
- One fewer wiring idiom to know: `pywire.fastapi` now exports a single public name.
- **New footgun, in tests only**: a `TestClient(app)` without `with` binds nothing and
  fails *silently* rather than raising. Any future endpoint test that skips the
  `api_client` fixture can pass while exercising the wrong container. Mitigated by the
  fixture and by item 5, not by the type system.
- The `pywire` upgrade path stays explicit (`uv lock --upgrade-package pywire` plus a tag
  bump), per ADR 0016 item 1 — unchanged.
- **Process gap this exposed, worth naming**: spec 0012's Feasibility Evidence carries
  per-item verification dates and commits, but nothing re-checks them when a pinned
  dependency moves. Two of its statements had been false since the 0.6.0 bump and were
  only caught by an explicit re-verification pass. No mechanism is introduced here to
  close that gap; it is recorded so the next dependency bump treats
  "re-verify the specs that cite this dependency" as part of the bump.
