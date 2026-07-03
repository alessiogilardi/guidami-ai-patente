# How to write a plan

## Always use the `write-plan` skill

Any time a plan must be **created, modified, or updated** — including status changes,
step edits, or restructuring — invoke the `write-plan` skill via the Skill tool
**before** touching any file:

```
Skill({ skill: "write-plan" })
```

The skill contains the authoritative, up-to-date specification for plan format,
frontmatter, structure, DoD rules, and the full workflow. Do **not** follow the
old rules in this file — they are superseded by the skill.

## `docs/plans/_index.md` — never edit manually

`docs/plans/_index.md` is managed exclusively by the `write-plan` skill.
Do not edit it by hand: the skill handles index updates as part of its workflow.
