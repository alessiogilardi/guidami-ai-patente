# Sub-plans (long plans)

If a plan exceeds the `XL` effort threshold (see ## Effort — Calibration) or covers
distinct independent areas, it must be split into sub-plans:

1. Use `create_plan.py` with `--subdir <topic-slug>` and `--step <N>` to scaffold each
   sub-plan. The script creates (or reuses) the dated sub-directory and generates a stub
   `_index.md` if one does not yet exist.
2. Fill in the `_index.md` with **discursive breakdown reasoning** — not a mechanical
   list. Explain why the feature was split, what each step covers, and how they relate
   to each other. The stub only provides the frontmatter and heading; the author writes
   all explanatory content.
3. Sub-plan files follow the same filename format: `YYYY-MM-DD--step-<NN>-<sub-slug>.md`.
4. `generate_index.py` treats the sub-directory as a single entry in the root index
   (sub-plans are not listed individually).

```markdown
docs/plans/
  _index.md                                  ← generated
  2026-07-01--ingest-quiz-enrichment/
    _index.md                                ← written by the author (discursive breakdown)
    2026-07-01--step-01-normalization.md
    2026-07-01--step-02-keyword-tagging.md
```

## Example usage

```bash
# First sub-plan — creates the sub-directory and _index.md stub:
uv run .claude/skills/write-plan/scripts/create_plan.py normalization \
    --subdir quiz-enrichment --step 1

# Second sub-plan — reuses the existing sub-directory:
uv run .claude/skills/write-plan/scripts/create_plan.py keyword-tagging \
    --subdir quiz-enrichment --step 2
```
