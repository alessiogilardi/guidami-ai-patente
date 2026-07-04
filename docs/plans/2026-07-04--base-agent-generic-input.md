---
status: Draft
effort: S
---
# Base Agent Generic Input

References:
- `src/commons/agents/base_agent.py`
- `tests/commons/agents/test_base_agent.py`

## Context and motivation

`BaseAgent[T_In: BaseModel, T_Out]` and `PromptRenderer` currently accept only Pydantic
`BaseModel` instances as input. This forces every caller to depend on Pydantic even when
a plain dataclass, a `dict`/`Mapping`, or a pre-rendered `str` prompt would suffice.
Generalising the input type removes the hard Pydantic coupling from the request side
while keeping full backwards compatibility with existing callers.

## Non-goals

- No changes to the output side (`T_Out` remains unconstrained).
- No changes to existing agent DTO classes (`RoadSignDescriberRequest`, etc.).
- No changes to the YAML agent configuration loading logic.
- No introduction of Protocol adapters or wrapper types.

## Decisions

**`PromptInput` type alias** — the accepted input union:
```
PromptInput = BaseModel | Mapping[str, Any] | str
```
`dataclass` instances satisfy this via internal detection (see below); callers do not need
to call `asdict()` themselves.

**Dispatch strategy in `PromptRenderer._to_vars()`** — ordered isinstance checks:
1. `BaseModel` → `.model_dump()` (Pydantic's own serialisation)
2. `is_dataclass(request) and not isinstance(request, type)` → `dataclasses.asdict()`
3. `Mapping` → pass through unchanged
4. `str` → return `None` (signals "bypass template substitution")

The `str` case bypasses `Template.safe_substitute` entirely; the string is used verbatim
as the rendered prompt. This is the correct semantic for pre-rendered prompts.

**`T_In` bound removed** — `BaseAgent[T_In: BaseModel, T_Out]` becomes
`BaseAgent[T_In, T_Out]`. The type constraint is now expressed via the `PromptInput`
alias in the `run`/`run_sync`/`__call__` parameter annotations.

## Open questions / Risks

None. All existing callsites use `BaseModel` subclasses, which remain valid members of
the `PromptInput` union. No breaking changes.

## Implementation tasks

### 1. Update `src/commons/agents/base_agent.py`

- Add `import dataclasses` and `from collections.abc import Mapping` at the top.
- Define `PromptInput = BaseModel | Mapping[str, Any] | str` type alias (module-level,
  before `PromptRenderer`).
- Add `PromptRenderer._to_vars(request: PromptInput) -> Mapping[str, Any] | None`
  private method with the 4-case dispatch.
- Rewrite `PromptRenderer.render()` to use `_to_vars()` internally; keep the public
  signature backward-compatible but widen `request` to `PromptInput`.
- Change `class BaseAgent[T_In: BaseModel, T_Out]` to `class BaseAgent[T_In, T_Out]`
  and update `run`, `run_sync`, `__call__` parameter type from `T_In` (unchanged) — the
  bound removal is the only change here.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):

- `test_prompt_renderer_renders_dataclass` — dataclass with matching field, assert
  substitution works.
- `test_prompt_renderer_renders_str_directly` — `str` input bypasses template, assert
  the raw string is returned unchanged.

## Definition of Done

Variable block (plan-specific):

- [ ] `PromptInput` alias defined at module level in `base_agent.py`
- [ ] `PromptRenderer._to_vars` handles all 4 branches (BaseModel, dataclass, Mapping, str)
- [ ] `BaseAgent` generic bound `T_In: BaseModel` removed
- [ ] New test cases cover dataclass and str inputs

Fixed block (same for every plan):

- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Agent `doc-architect` invoked (if available)
- [ ] Plan updated to `status: Implemented`
