# ADR 0032: Extend pywire's DI scope to the Telegram bot

## Status

Superseded by ADR 0033

## Context

Spec 0015 (`docs/superpowers/specs/2026-09-15-telegram-bot-client-design.md`)
introduces `src/guidami_ai_patente_bot/`, a new top-level package: a
Telegram bot that is the first real user-facing client of the
`guidami_ai_patente` API. Like the FastAPI app, it is a long-running process
that resolves the same handful of components (a config, an HTTP client to
the API, an orchestration service) once at startup and reuses them across
every incoming Telegram update — the same request/update-scoped shape ADR
0015 used to justify pywire for `guidami_ai_patente`, and not the
batch/one-shot execution model that keeps `commons/` and
`guidami_ai_patente_ingestor/` on manual constructor injection
(`.claude/rules/dependency-injection.md`).

ADR 0015 scoped pywire deliberately narrowly ("this scope is deliberately
narrow: `guidami_ai_patente_ingestor/` and `commons/` keep manual constructor
injection unchanged"), so widening it to a second package is a scope change
that needs its own record rather than a silent extension.

Separately, building the bot exposed a real gap: pywire (pinned at `v0.8.0`
in `pyproject.toml`, currently the latest tag published on the `pywire`
repository — verified via `git ls-remote --tags`, no newer tag exists) has no
released support for a component that is itself an async context manager.
`PostgresClientProvider` sidesteps this today because `PostgresClient`'s pool
is opened/closed synchronously (`ConnectionPool.open`/`.close`), torn down via
a plain synchronous `@pre_destroy` hook (`.claude/rules/pywire-di.md`). The
bot's `QuizApiClient` wraps an `httpx.AsyncClient`, whose clean shutdown is
`await client.aclose()` — an async operation `@pre_destroy` has no documented
support for today.

## Decision

Extend pywire's DI scope to `src/guidami_ai_patente_bot/`, in addition to
`src/guidami_ai_patente/`. The bot's instantiable components follow the same
convention `pywire-di.md` documents for the API: `BotConfig` is loaded once
in `main.py` and registered on the container via `register_instance`
(never autowired as if it constructed itself); `QuizApiClient` is decorated
`@client`; `QuizFlowService` is decorated `@service`; both declare their
dependencies as `Autowired[T]` fields. `commons/` and
`guidami_ai_patente_ingestor/` are unaffected — they keep manual constructor
injection unchanged; this decision only widens the set of packages pywire
applies to, it does not revisit that choice for the other two.

`pywire-di.md`'s scope statement is updated from "scoped to
`src/guidami_ai_patente/` only" to cover both `guidami_ai_patente` and
`guidami_ai_patente_bot`, still excluding `commons/` and the ingestor.

Async-context-manager component support is explicitly **not** part of this
decision: it does not exist in any published pywire release, and adding it
is upstream work in the `pywire` repository itself, out of scope for this
repo and this ADR. Until it ships, `QuizApiClient`'s underlying
`httpx.AsyncClient` is closed with an explicit `await` in
`guidami_ai_patente_bot/main.py`'s own shutdown sequence, outside of any
pywire teardown hook — a known, deliberately deferred gap, not a workaround
pywire is expected to absorb silently later.

## Alternatives considered

- **Manual constructor injection for the bot, matching the
  ingestor/`commons/` convention**: keeps pywire's footprint exactly as ADR
  0015 left it, but the bot's shape (long-running process, composition root
  resolved once, request/update-scoped handlers) is the same one that made
  constructor injection a poor fit for the FastAPI app in ADR 0015 — the
  same argument applies here, not a different one.
- **Wait for pywire's async-context-manager support before starting the bot
  at all**: blocks the bot's MVP on unscheduled work in a separate repo with
  no committed timeline; rejected as disproportionate to what the MVP
  actually needs (the bot has nothing today that requires true async
  teardown beyond one `httpx.AsyncClient`, which a manual `await` in
  `main.py` closes correctly).

## Consequences

- pywire's field-injection style now spans two packages
  (`guidami_ai_patente`, `guidami_ai_patente_bot`) instead of one;
  `commons/` and `guidami_ai_patente_ingestor/` remain the deliberate
  exception, unchanged from ADR 0015.
- The bot carries one manually-managed async resource
  (`QuizApiClient`'s `httpx.AsyncClient`) outside of pywire's teardown
  mechanism. If a second async resource needing the same treatment appears
  before pywire adds native support, that duplication is the concrete
  trigger to revisit this ADR rather than copy the workaround a third time.
- `pywire-di.md` needs a scope-statement edit (via `second-brain:update`)
  once this ADR lands, so the rule file and this ADR do not drift apart.
