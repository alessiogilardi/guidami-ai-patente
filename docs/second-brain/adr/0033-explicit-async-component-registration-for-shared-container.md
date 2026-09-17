# ADR 0033: Register `QuizApiClient` explicitly, not via the `@async_component` decorator

## Status

Proposed

## Context

ADR 0032 extended pywire's DI scope to `src/guidami_ai_patente_bot/` and
decided `QuizApiClient` would be a pywire `@async_component` once that
capability shipped (pywire 0.9.0). The telegram-bot-client-mvp plan
implemented exactly that: `QuizApiClient` was decorated `@async_component`
at class-definition time, following the same pattern every other pywire bean
in this repo uses (`@service`, `@client`, `@repository` all register on
`get_default_container()` the moment their module is imported).

This broke `uv run pytest` — this repo's documented, single test command —
for the whole `guidami_ai_patente` API test suite, discovered only by the
plan's final whole-branch review (invisible to any single-task review, which
only ever saw one package's test tree in isolation). The mechanism:
`get_default_container()` returns a process-wide singleton
(`pywire/container.py::get_default_container`). `guidami_ai_patente`'s
FastAPI app (`api/app.py`) runs `FastAPI(lifespan=pywire_lifespan)` against
that same default container; `pywire_lifespan`'s `astart()` enters every
`@async_component` registered on it. Merely *importing*
`guidami_ai_patente_bot.clients` — which happens as soon as pytest collects
both `tests/guidami_ai_patente` and `tests/guidami_ai_patente_bot` in one
invocation, exactly what a plain `uv run pytest` does — registered
`QuizApiClient` on the shared container via the decorator. The API's own
`astart()` then tried to enter it too and failed:
`DependencyResolutionError: Cannot resolve 'BotConfig': it is not
registered in this container. Required by 'QuizApiClient.config'` — nothing
in the API's composition root registers `BotConfig`, since it's the bot's
config, not the API's.

In production the two apps run as separate OS processes (`uv run serve` vs
`uv run telegram-bot`), each with its own Python interpreter and therefore
its own `_default_container` singleton — this bug has no production runtime
impact. It is specifically a shared-test-process problem, but it breaks the
repo's actual, documented verification command, which is enough to block a
merge on its own.

## Decision

`QuizApiClient` (`src/guidami_ai_patente_bot/clients/quiz_api_client.py`) is
**not** decorated with `@async_component`. It is registered explicitly, at
runtime, from the bot's own composition root:
`get_default_container().register_async_component(QuizApiClient)`, called
in `main.py::_run`, after `BotConfig` is loaded and `register_instance`d,
and before `container.lifespan()` is entered. Merely importing
`guidami_ai_patente_bot.clients` (or any module that transitively imports
it) now has no side effect on any container — registration only happens
when the bot's own entry point actually runs.

This is a narrow, class-specific exception to the blanket convention in
`.claude/rules/pywire-di.md` ("every service/repository/client/router-
dependency class... is decorated with the role-appropriate pywire
decorator"). `QuizFlowService` (`@service`) is unaffected and keeps the
decorator: it is sync, only built lazily on `resolve()`, and registering it
at import time carries no equivalent risk — the risk here is specific to
`register_async_component`'s interaction with `astart()` entering every
async-managed bean unconditionally.

## Alternatives considered

- **Keep the `@async_component` decorator (ADR 0032's original design)**:
  simplest, most consistent with every other pywire bean in this repo — but
  it is exactly what breaks `uv run pytest`, and the failure mode is
  collection-order-dependent and silent until both test trees happen to be
  imported together. Rejected: the whole point of a shared default container
  is that "shared" is not optional once two apps both use one, and this
  decorator's side effect assumes it's the only app doing so.
- **Give the bot its own separate `Container()` instance instead of the
  global default**: sidesteps the collision at the root — the bot's
  container would never see the API's beans or vice versa. Rejected: every
  bot handler and test in this codebase already resolves against
  `get_default_container()` (per `.claude/rules/pywire-di.md`'s "the pywire
  default container is deliberately the app's composition root"), so this
  would mean threading a non-default `Container` instance through every
  handler and test fixture — a much larger, more invasive change for the
  same outcome the explicit-registration fix achieves in two lines.
- **Register a throwaway `BotConfig` on the default container from a
  session-scoped autouse fixture in the API's own `tests/conftest.py`**:
  a one-line fix, but it papers over the actual architectural coupling (two
  independent apps sharing one process-global container the moment they're
  imported together) instead of removing it, and it would silently
  construct a bot HTTP client in every API test session regardless of
  whether that session ever touches the bot. Rejected as a workaround for
  the symptom, not the cause.

## Consequences

- `QuizApiClient` is the one bean in this repo whose pywire registration
  lives outside its own class definition, at its app's composition root
  instead. A reader expecting "grep the decorator to find every registered
  bean" needs to know this one exception — `.claude/rules/pywire-di.md` and
  `docs/second-brain/layout.md`/`architecture.md` all now document it, and
  the class's own docstring explains why.
- If a second async-context-manager bean is ever added to
  `guidami_ai_patente_bot/`, it needs the same explicit-registration
  treatment (and the same reasoning applies to any future second app that
  shares this process-wide default container with an existing one) — this
  is the concrete trigger to promote "explicit registration for a bean
  whose module might be imported by more than one app" from a one-off
  exception into a documented `pywire-di.md` rule, rather than re-deriving
  the reasoning from scratch each time.
- **Candidate upstream improvement (pywire itself), not decided or scheduled
  here**: today every bare decorator (`@component`, `@service`, `@client`,
  `@async_component`, ...) registers unconditionally on the one process-wide
  default container the moment its module is imported — safe for a single
  app per process, but exactly what breaks the moment two apps in the same
  repo/venv end up imported into one process together (as `uv run pytest`
  does here). A decorator mode that registers lazily instead of at
  import-time, or that binds to an explicitly-named/scoped container rather
  than always the module-level default, would let `@async_component` (and
  the other bare decorators) stay usable even in that situation, removing
  the need for this ADR's explicit-registration exception entirely. Worth
  floating as a pywire issue/feature request; not pursued as part of this
  plan, since it's out of scope for this repo's own codebase.
- Supersedes ADR 0032's `QuizApiClient` registration detail (its async-
  context-manager gap is now closed by pywire 0.9.0, as ADR 0032 itself
  anticipated) — but not ADR 0032's broader decision to extend pywire's DI
  scope to this package at all, which stands unchanged.
