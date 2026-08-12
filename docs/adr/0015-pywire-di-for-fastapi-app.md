# ADR 0015: pywire for dependency injection in the FastAPI app

## Status

Accepted

## Context

The `guidami_ai_patente/` FastAPI app (the quiz bot) is about to move from a
scaffolded layout into real development: `services/`, `repositories/`,
`models/`, `mappers/` are currently empty, pull-based packages with no
domain endpoints beyond `GET /health` (see `docs/architecture.md`).

The existing `guidami_ai_patente_ingestor/`/`commons/` codebase uses manual
constructor injection (`.claude/rules/dependency-injection.md`: plain data
first, dependencies last, no framework). A decision was needed on whether
the new FastAPI app should follow the same convention or adopt a different
one better suited to a web app with router-level dependency resolution.

## Decision

Adopt `pywire` — a Spring Boot-style IoC container (git dependency, see
`pyproject.toml`) — for dependency injection in `src/guidami_ai_patente/`
only. Classes are registered via role-appropriate decorators
(`@service`/`@repository`/`@client`/`@component`) and declare their
dependencies as class-level `Autowired[T]` fields, resolved from the
process-wide default container after instantiation, rather than as
constructor parameters. Full convention documented in
`.claude/rules/pywire-di.md`.

This scope is deliberately narrow: `guidami_ai_patente_ingestor/` and
`commons/` keep manual constructor injection unchanged
(`.claude/rules/dependency-injection.md`).

## Alternatives considered

- **Reuse the ingestor's manual constructor injection in the FastAPI app
  too**: keeps the whole codebase on one DI style, but constructor
  injection composes awkwardly with FastAPI's own request-scoped `Depends`
  resolution at the router boundary; the Spring-style field-injection
  pattern was preferred for the web layer specifically.

## Consequences

- Two DI styles coexist in the repo: constructor injection in
  `guidami_ai_patente_ingestor/`/`commons/`, field injection via `pywire`
  in `guidami_ai_patente/`. This is documented (`.claude/rules/pywire-di.md`)
  precisely so the two are not "harmonized" into one by mistake.
- An extra external git dependency (`pywire`) is added to `pyproject.toml`.
- `AppConfig` stays plain data, loaded once at the entry point and exposed
  to the container rather than autowired as a component itself — keeps the
  existing "config loaded at entry point" rule intact even under the new
  DI style.
