"""Infrastructure components implementing a technical contract (spec 0013, AD-16).

Infrastructure components implementing a contract the inner layers (a `UseCase`,
a `*Service`, the domain) rely on, to supply a technical service or access to an
external resource — while those inner layers stay unaware of the implementation
detail behind it (AD-16, revised; full definition in
`.claude/rules/pywire-di.md`'s "`@provider`" section). The test is the direction of
the dependency, not constructor arity: a provider *supplies* something, it never
*decides* something — a class that branches on a business rule stays a `@service`/
`UseCase` even if it also hands back a resource (see `QuizImageService`).

Distinct from a `repository` (parameterized reads against a store — no caller wants
the repository's own collaborators, they want a read result) and a `client` (a thin
adapter to an external API or a resource still owned by a pre-pywire package, e.g.
`guidami_ai_patente/clients/postgres_client_provider.py::PostgresClientProvider`,
which fits this definition conceptually but keeps `@client` and stays in `clients/`
pending `commons/` itself adopting pywire).

`LabelingStackProvider` is the reference example: what it exposes — the loaded
`AgentConfig` plus the `LabelingEpoch` derived from it — is a value multiple
consumers (the FR-8 precedence query, the FR-14 startup check) read without knowing
how it was built, built once at first resolution rather than re-read per caller.
"""

from .labeling_stack_provider import LabelingStackProvider

__all__ = ["LabelingStackProvider"]
