---
paths:
  - "src/guidami_ai_patente_ingestor/cli/**"
---

# CLI structure — self-contained package

The `cli/` package (`src/guidami_ai_patente_ingestor/cli/`) is **self-contained**:
components that exist only to serve the CLI live **inside** `cli/`, replicating the
project's layered structure locally rather than being placed in the global top-level
packages.

```
cli/
  __init__.py        # re-exports main → entry point "...cli:main" stays valid
  main.py            # entry point: logging, config load, parse, dispatch
  parser.py          # argparse construction (config-driven)
  wiring.py          # lazy DI builders (clients/providers/repos), built per command
  commands/          # one thin controller per subcommand
  services/          # CLI-only domain services (e.g. status readiness/health)
  models/            # CLI-only DTOs (e.g. readiness/health value objects)
  rendering/         # presentation layer (rich)
```

## Rule

- **Self-contained by default.** A new service, model, or other component introduced
  for a CLI feature and used **only** by the CLI goes under `cli/services/`,
  `cli/models/`, etc. — not in the global `src/<app>/services/` or `models/`. This keeps
  the feature a cohesive, removable vertical slice and avoids polluting the global
  packages with CLI-only concerns.

- **Shared infrastructure stays in its own top-level layer.** If a component is genuinely
  shared with the pipelines or other consumers, it belongs in the appropriate global
  package, not in `cli/`. Example: read primitives (`table_exists`, `row_count`) added to
  `BulkInsertStoreRepository` live in `repositories/db/` because that base already serves
  the ingestion pipelines — the CLI merely consumes them.

- **The deciding test**: "is this used by anything other than the CLI?" No → `cli/`.
  Yes → the shared layer.

## Imports

The general import rules (`~/.claude/rules/python/imports.md`) apply unchanged: relative
imports within the same `cli/` sub-package, absolute imports when crossing a package
boundary (e.g. importing `IngestorConfig`, `LayerResolverProvider`, or a repository from outside
`cli/`).
