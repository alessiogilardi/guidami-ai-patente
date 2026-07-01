# How to write a plan
These rules apply to anyone writing or editing a plan in `plans/`.

## Location and file name
Plans must be written **exclusively in `<project-root>/plans/`** — the `plans/`
directory at the root of *this* project, not any global or system-level
directory. Use a descriptive, self-explanatory file name, do not use generic names like `plan.md`.

After creating the file, add a pointer to it in `plans/_index.md`.

## Frontmatter
Every plan starts with a YAML frontmatter that tracks its status:
```yaml
---
status: Draft | Reviewed | Implemented | Archived
---
```

| Status | Meaning |
|---|---|
| `Draft` | Being written, not ready for implementation |
| `Reviewed` | Discussed and approved — ready for implementation |
| `Implemented` | Code completed and `architecture-doc-keeper` updated |
| `Archived` | Superseded or abandoned (state the reason/replacement plan in the text) |

## Expected structure
```
---
status: Draft
---
# Title
References: links to related plans and architectures.

## Context and motivation
Why this plan is needed. What the current problem is.

## Decisions
1. **Decision 1** — rationale.
2. **Decision 2** — rationale.

## Implementation steps
### 1. Step title
Description of the change with target file/class.

**Tests:**
- Add: `tests/path/test_file.py::test_name` — behavior verified
- Modify: `tests/path/test_file.py::test_name` — why it changes
- Remove: `tests/path/test_file.py::test_name` — why it's no longer valid

### 2. Step title
...

## Definition of Done
- [ ] `grep -r "OldSymbol" src/` → zero matches
- [ ] `from package.module import NewClass` resolves
- [ ] `uv run pytest` green (including new tests covering the behavior)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Plan updated to `status: Implemented`
- [ ] `architecture-doc-keeper` invoked
```

## DoD rules
The DoD is always the **last section** of the plan. Every item must be
verifiable with a command (`grep`, `uv run pytest`, `python -c "import ..."`)
— no subjective criteria.

## Full workflow
1. Write the plan with `status: Draft`
2. Add the pointer to `plans/_index.md`
3. Have the plan reviewed → update to `status: Reviewed`
4. Generate failing TDD tests with the `tdd-test-writer` agent
5. Implement (`python-developer` agent or manually)
6. Verify **mechanically** every DoD item
7. Invoke the `architecture-doc-keeper` agent — do not edit
   `.claude/architectures/` directly
8. Update the plan to `status: Implemented`