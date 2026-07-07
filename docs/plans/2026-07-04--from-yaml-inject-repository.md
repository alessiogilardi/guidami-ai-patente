---
status: Archived
effort: L
---
# From Yaml Inject Repository

_Archived: fully implemented and shipped (see DoD below); kept for historical reference._

## Context and motivation

`BaseAgent.from_yaml` currently builds a `YamlRepository` internally from an `agents_dir: Path`
argument. This violates the project's dependency-injection convention where repositories are
constructed by the caller and injected — not created inside components. Aligning `from_yaml` to
this pattern makes the method consistent with all other `from_yaml` / factory methods in the
codebase and lets callers share or pre-configure the repository independently of the agent.

## Non-goals

- No changes to `BaseAgent.__init__` or any runtime agent behaviour.
- No changes to `YamlRepository` or any other repository class.
- No changes to the `AgentConfig` model.

## Decisions

- `from_yaml` receives a `YamlRepository` (already typed as `YamlRepository[AgentConfig]` via
  inference) instead of `agents_dir: Path`. The `YamlRepository` is constructed by the caller.
- Subclass overrides mirror the same signature change: `agents_dir: Path` → `repository: YamlRepository`.
- The `# type: ignore[override]` comment on subclass overrides is removed: after the change the
  signatures are compatible and the suppression is no longer needed.
- Flow call sites construct the repository inline (one `YamlRepository` per flow function, reused
  for all agents in that function).
- Tests that receive `agents_dir` via fixture: update the fixture to return `YamlRepository` if the
  fixture is used exclusively for `from_yaml` calls; otherwise wrap at each call site. The
  implementer should check fixture usage before deciding.

## Open questions / Risks

None. The refactor is mechanical and fully covered by existing tests.

## Implementation tasks

### 1. Update `BaseAgent.from_yaml` in `src/commons/agents/base_agent.py`

Replace `agents_dir: Path` with `repository: YamlRepository` and remove the internal
`YamlRepository` construction:

```python
# Before
def from_yaml(cls, name: str, agents_dir: Path, output_type: type[T_Out]) -> ...:
    repository = YamlRepository(agents_dir, AgentConfig)
    config = cast(AgentConfig, repository.load(f"{name}.yaml"))
    return cls(config, output_type)

# After
def from_yaml(cls, name: str, output_type: type[T_Out], repository: YamlRepository[AgentConfig]) -> ...:
    config = cast(AgentConfig, repository.load(f"{name}.yaml"))
    return cls(config, output_type)
```

`YamlRepository` and `AgentConfig` are already imported; no new imports needed.
Update the docstring: remove the `agents_dir` arg description, add `repository`.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):

- `test_base_agent_from_yaml_factory_method`: construct `YamlRepository(agents_dir, AgentConfig)`
  before calling `BaseAgent.from_yaml`.
- `test_base_agent_from_yaml_raises_file_not_found`: same wrapper.
- Any other `BaseAgent.from_yaml` call in `tests/commons/agents/test_base_agent.py`.

### 2. Update three agent subclass overrides

Files: `src/guidami_ai_patente_ingestor/agents/`
- `article_contextualizer_agent.py`
- `road_sign_describer_agent.py`
- `norm_reference_describer_agent.py`

For each file apply the same mechanical change:

```python
# Before
from pathlib import Path
...
def from_yaml(cls, name: str, agents_dir: Path) -> "XxxAgent":  # type: ignore[override]
    return super().from_yaml(name, agents_dir, output_type=XxxResponse)  # type: ignore[return-value]

# After
from commons.repositories import YamlRepository
...
def from_yaml(cls, name: str, repository: YamlRepository) -> "XxxAgent":
    return super().from_yaml(name, repository, output_type=XxxResponse)  # type: ignore[return-value]
```

Remove `from pathlib import Path` if it is the only `Path` usage in the file.
Remove `# type: ignore[override]` from the `def` line (signatures now compatible).
Update docstring: replace `agents_dir` arg with `repository`.

**Tests** (intent, not contract):

- `tests/guidami_ai_patente_ingestor/agents/test_article_contextualizer_agent.py`: update all
  `ArticleContextualizerAgent.from_yaml(name, agents_dir)` calls to pass a `YamlRepository`.
- `tests/guidami_ai_patente_ingestor/agents/test_road_sign_describer_agent.py`: same for
  `RoadSignDescriberAgent.from_yaml`.

### 3. Update flow call sites

Files:
- `src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py` (line 236)
- `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py` (lines 224–227)

For each flow function that calls `from_yaml`, construct a repository once and reuse it:

```python
# knowledge_flows.py — before
agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", config.agents_dir)

# knowledge_flows.py — after
agents_repository = YamlRepository(config.agents_dir, AgentConfig)
agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", agents_repository)
```

```python
# quiz_flows.py — before
describer = RoadSignDescriberAgent.from_yaml("road_sign_describer", config.agents_dir)
norm_describer = NormReferenceDescriberAgent.from_yaml("norm_reference_describer", config.agents_dir)

# quiz_flows.py — after
agents_repository = YamlRepository(config.agents_dir, AgentConfig)
describer = RoadSignDescriberAgent.from_yaml("road_sign_describer", agents_repository)
norm_describer = NormReferenceDescriberAgent.from_yaml("norm_reference_describer", agents_repository)
```

Add imports `from commons.repositories import YamlRepository` and `from commons.configs import AgentConfig`
to each flow file (if not already present).

**Tests**: `test_knowledge_preparation_flows.py` and `test_quiz_preparation_flows_v2.py` use
`patch.object(..., "from_yaml", ...)` — they patch by name only, so no changes needed.

## Definition of Done

Variable block (plan-specific):

- [ ] `grep -r "agents_dir" src/` returns no hits in `base_agent.py` or agent subclass files
- [ ] `grep -r "type: ignore\[override\]" src/guidami_ai_patente_ingestor/agents/` returns no hits
- [ ] `grep -r "from pathlib import Path" src/guidami_ai_patente_ingestor/agents/` returns no hits (unless Path is used elsewhere in a file)

Fixed block (same for every plan):

- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Agent `doc-architect` invoked (if available)
- [ ] Plan updated to `status: Implemented`
