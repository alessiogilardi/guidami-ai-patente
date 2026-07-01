# How to write a plan
These rules apply to anyone writing or editing a plan in `plans/`.

## Location and file name
Plans must be written **exclusively in `<project-root>/docs/plans/`** — not any
global or system-level directory. Use a descriptive, self-explanatory file name;
do not use generic names like `plan.md`.

**File name format**: `YYYY-MM-DD--<descriptive-slug>.md` — the creation date
comes first so plans sort chronologically.
Examples: `2026-07-01--ingest-quiz-enrichment.md`, `2026-07-15--hybrid-retrieval-rrf.md`.

After creating the file, add a pointer to it in `docs/plans/_index.md`.

### Long plans — splitting into sub-plans

If a plan becomes too long or covers distinct areas, it can be split into sub-plans:

1. Create a subfolder in `docs/plans/` using the same date-slug format:
   `docs/plans/YYYY-MM-DD--<topic>/`
2. Add an `_index.md` in the subfolder describing the parent plan and linking the sub-plans.
3. Sub-plan files follow the same format: `YYYY-MM-DD--<sub-slug>.md`.
4. Add a single pointer to the subfolder in `docs/plans/_index.md`
   (do not list each sub-plan individually in the root index).

Example:
```
docs/plans/
  _index.md
  2026-07-01--ingest-quiz-enrichment/
    _index.md                              ← describes the overall plan, links sub-plans
    2026-07-01--step-01-normalization.md
    2026-07-01--step-02-keyword-tagging.md
```

## Frontmatter
Every plan starts with a YAML frontmatter that tracks its status:
```yaml
---
status: Draft | Reviewed | Implemented | Archived
creation_date: YYYY-MM-DD
last_update_date: YYYY-MM-DD
effort: S | M | L | XL
---
```

| Status | Meaning |
|---|---|
| `Draft` | Being written, not ready for implementation |
| `Reviewed` | Discussed and approved — ready for implementation |
| `Implemented` | Code completed and `doc-architect` agent invoked |
| `Archived` | Superseded or abandoned (state the reason/replacement plan in the text) |

## Expected structure
```
---
status: Draft
creation_date: YYYY-MM-DD
last_update_date: YYYY-MM-DD
effort: S | M | L | XL
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
- [ ] `doc-architect` agent invoked
```

## DoD rules
The DoD is always the **last section** of the plan. Every item must be
verifiable with a command (`grep`, `uv run pytest`, `python -c "import ..."`)
— no subjective criteria.

## Full workflow
1. Write the plan with `status: Draft`
2. Add the pointer to `docs/plans/_index.md`
3. Have the plan reviewed → update to `status: Reviewed`
4. Generate failing TDD tests with the `tdd-test-writer` agent
5. Implement (`python-developer` agent or manually)
6. Verify **mechanically** every DoD item
7. Invoke the `doc-architect` agent — do not edit
   `docs/architecture/` directly
8. Update the plan to `status: Implemented`