# Dependency Injection — constructor argument order

Injected dependencies (services, repositories, clients, agents — collaborating
components with behavior, typically mocked in tests) **must be the last
arguments** of `__init__` / factory methods (`get_instance`, `from_yaml`, ...).

Plain data — `name`, string/bool/int flags, `Path`, model classes (`type[T]`),
enums, `Literal` values, and Pydantic config/settings objects — comes first.

```python
# WRONG — dependency (repository) sandwiched between plain args
def __init__(self, name: str, repository: KnowledgeChunkStoreRepository, source: str) -> None: ...

# RIGHT — plain args first, dependency last
def __init__(self, name: str, source: str, repository: KnowledgeChunkStoreRepository) -> None: ...
```

Rationale: keeps the identity/config parameters grouped together and the
swappable collaborator in the position readers scan for first when looking
for what to mock in a test.

## Config objects are not "dependencies"

A Pydantic config/settings object (e.g. `AgentConfig`, `PostgresConnectionConfig`)
is data, not a collaborator — it is not subject to this rule and keeps whatever
position makes sense (usually first, per `rules/python/architecture.md`).

## Applies to

`src/commons/` and `src/guidami_ai_patente_ingestor/` (services, repositories,
clients, agents, orchestrator steps). Does **not** apply to `flowstep`
(`Step`, `Flow`, `FlowBuilder`, ...): it's a generic, domain-agnostic
pipeline framework whose constructors don't take service/repository
dependencies, and it's an external git dependency, not code in this repo.

When a constructor takes two dependencies (e.g. `layer_resolver` and
`repository` in `LoadJsonStep`/`WriteJsonStep`), both go at the end, after all
plain args, in whatever relative order reads best.
