# Standalone stateless functions — always `utils/`, even domain-specific ones

A module made up entirely of standalone, stateless functions — no injected config, no
dependency, nothing that would stop every one of them from being a `@staticmethod` if
they were forced into a class — belongs in a `utils/` subpackage of its owning
top-level package, never in `services/`. This holds even when the functions encode
domain-specific logic (a CdS/CAP-only regex, a repeal formula) rather than something
generically reusable.

This narrows `~/.claude/rules/python/architecture.md`'s global rule for this project:
that file reserves `utils/` for "genuinely generic" helpers and tells domain-specific
stateless logic to live in its domain package as a class. In practice, this project
does the opposite for a module that is *already* a bare function (not wrapped in a
class) — see the two precedents below, both moved out of `services/` on exactly this
reasoning.

```
services/  # classes with injected config/dependencies, or a named pipeline step
utils/     # standalone functions with no injected state — domain-specific is fine
```

## Precedents

- `src/guidami_ai_patente_ingestor/utils/comma_repeal_detector.py` —
  `is_comma_repealed`/`detect_comma_repeal`, CdS/CAP-specific, moved out of
  `services/knowledge/`. Still re-exported from `services/knowledge/__init__.py` so
  call sites read it alongside `ArticleCleanerService`, unchanged.
- `src/glossary/utils/chunking.py` — `split_into_chunks`, mechanical CdS/CAP
  enumeration-marker chunking (AD-10), moved out of `services/_chunking.py`.

## How to apply

- New standalone pure-function module → `utils/`, package-`__init__.py`-exported,
  regardless of how domain-specific its logic is.
- If the function is tightly coupled to one service's call site and re-exporting it
  from that service's own `__init__.py` improves readability there, do both — `utils/`
  is still its home, the service re-export is only for call-site cohesion (see
  `comma_repeal_detector` above).
- A class stays in `services/` only when it has injected config/dependencies, or is an
  explicit named dependency of a pipeline/DI container per the "Class vs function"
  exception in `~/.claude/rules/python/architecture.md`.
