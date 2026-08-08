"""Self-contained FastAPI web layer: app factory, routers, and API-only schemas.

Mirrors the `cli/` package convention (`.claude/rules/cli-structure.md`): components
that exist only to serve the HTTP API live here, replicating the project's layered
structure locally rather than polluting the top-level `services/`/`models/` packages.
"""
