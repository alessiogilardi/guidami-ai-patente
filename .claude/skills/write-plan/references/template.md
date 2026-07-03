# Plan structure

```markdown
---
status: Draft
effort: S | M | L | XL
---
# Title

References: links to related plans and architecture documents.

## Context and motivation
Why this plan is needed. What the current problem is.

## Non-goals
What this plan explicitly does NOT cover. Prevents scope from silently expanding
during implementation.

## Decisions
1. **Decision 1** — rationale.
2. **Decision 2** — rationale.

## Open questions / Risks
Unresolved uncertainties, known risks. If a decision has not yet been made,
it belongs here — not in the Decisions section disguised as a final choice.

## Implementation tasks
### 1. Task title
Description of the change with target file/class.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- Add: `tests/path/test_file.py::test_name` — behaviour verified
- Modify: `tests/path/test_file.py::test_name` — why it changes
- Remove: `tests/path/test_file.py::test_name` — why it is no longer valid

### 2. Task title
...

## Definition of Done

Variable block (plan-specific):

<!-- Add plan-specific, mechanically verifiable items here -->

Fixed block (same for every plan):

- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Agent `doc-architect` invoked (if available)
- [ ] Plan updated to `status: Implemented`
```
