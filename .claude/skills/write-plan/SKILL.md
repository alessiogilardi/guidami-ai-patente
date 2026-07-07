---
name: write-plan
description: Write, review, or update technical implementation plans for the project. Use this skill every time the user asks to "write a plan", "plan" a feature/refactor, create or modify files in docs/plans/, update a plan status (Draft/Reviewed/Implemented/Archived), or split a long plan into sub-plans. Always invoke it BEFORE writing any file inside docs/plans/, even if the user does not explicitly mention this skill. If no confirmed Understanding card file exists yet for the slug (docs/plans/.brainstorm/<slug>.md with confirmed true), this skill invokes the brainstorm skill first.
allowed-tools:
  - Skill
  - Read
  - Glob
  - "Bash(uv run .claude/skills/write-plan/scripts/*)"
---

# Writing Plans

> **Language rule**: All plan files must be written in **English** — this applies regardless of the language used in the conversation with the user.

## Detailed Workflow

**Process Checklist**:

Create a task for each of these items and complete them strictly in order:

1. **Ensure Understanding**: Check that a confirmed Understanding card file exists at `docs/plans/.brainstorm/<slug>.md` (`confirmed: true`); if not, invoke the `brainstorm` skill first.
2. **Approach proposals**: Present 2–3 options with trade-offs and your recommendation.
3. **Design presentation**: Present design proportional to effort; get approval (single message for S/M; macro-sections for L/XL — see Design Presentation below).
4. **Scaffolding**: Run `create_plan.py` to create the plan file and regenerate the index.
5. **Write plan content**: Fill in all sections following the conventions below.
6. **Validate**: Run `validate_plan.py` until it exits 0.
7. **Self-review**: Verify the absence of placeholders, contradictions, or ambiguities.
8. **User review**: Ask the user to review the final plan file before proceeding with implementation.

---

### Step 0 — **Ensure Understanding (delegate to `brainstorm`)**

`write-plan` never runs its own discovery conversation — that responsibility belongs entirely to the [`brainstorm`](../brainstorm/SKILL.md) skill, which explores context, asks scoping questions one at a time, and persists a confirmed **Understanding card** (Problem/Motivation, Non-Goals, Affected Areas, Success Criteria, Effort) to `docs/plans/.brainstorm/<slug>.md` after the user explicitly confirms *slug* and *effort*.

Before doing anything else:

* If a card file exists at `docs/plans/.brainstorm/<slug>.md` with `confirmed: true` in its frontmatter, skip straight to Step 1 — the file survives session restarts, so a brainstorm confirmed in an earlier conversation is still valid.
* Otherwise, invoke the `brainstorm` skill (Skill tool, `skill: "brainstorm"`) and wait for it to produce the confirmed card file before proceeding.

#### **Blocking Gate (Non-Negotiable Rule):**
**ABSOLUTE PROHIBITION:** Do not run `create_plan.py` (or any scaffolding command/script) until a confirmed card file exists — the script enforces this mechanically (it exits with an error if the card is missing, unconfirmed, or its effort contradicts `--effort`). Never work around that error by creating or editing anything in `docs/plans/.brainstorm/` yourself: only `brainstorm`'s `create_card.py` writes cards, and only after the user's explicit confirmation in chat.

---

### Step 1 — **Exploration and Design**

#### Approach Exploration

* Propose 2–3 different approaches highlighting their trade-offs.
* Present options conversationally, clearly stating your recommendation and the reasoning behind it.
* Always start by presenting the recommended option and explaining why.

#### Design Presentation

* Once requirements are agreed upon, present the system design.
* Modulate the length of each section based on its complexity: a few sentences if straightforward, up to 200–300 words if it has complex elements or technical nuances.
* **For S and M plans**, present the whole design in one message and request a single approval before proceeding.
* **For L and XL plans**, present the design in macro-sections (e.g. architecture + components, data flow + error handling, testing) and request approval after each macro-section, not after every subsection.
* The design must comprehensively cover: architecture, components, data flow, error handling, and testing.

#### Design for Isolation and Clarity

* Divide the system into smaller units, each with a single clear purpose, communicating through well-defined interfaces and independently testable.
* For each unit you must be able to clearly answer: *what it does*, *how it is used*, and *what it depends on*.
* If you cannot understand what a unit does without reading its internal implementation, or if modifying its internals breaks its callers, the structural boundaries need redesigning.
* Smaller units reduce cognitive load and make file edits more targeted and reliable.

#### Working on Existing Codebases

* Thoroughly explore the current structure before proposing changes, and always follow existing project patterns.
* If the existing code has structural problems that affect the current work (e.g. files too large, confused responsibilities, unclear boundaries), include targeted and localized improvements as part of the design.
* **Do not propose unrelated refactoring**: stay strictly focused only on what is needed to reach the current goal.

#### Key Principles

- **Group related questions** — Independent questions may be grouped, 2–4 at a time, in a single AskUserQuestion call; ask strictly one at a time only when an answer determines the next question
- **Multiple choice preferred** — Easier to answer than open-ended when possible
- **YAGNI ruthlessly** — Remove unnecessary features from all designs
- **Explore alternatives** — Always propose 2–3 approaches before settling
- **Incremental validation** — Present design, get approval before moving on
- **Be flexible** — Go back and clarify when something doesn't make sense

---

### Step 2 — **Scaffolding (mandatory, via script)**

Run `uv run .claude/skills/write-plan/scripts/create_plan.py <confirmed-slug>` — the effort is inherited from the confirmed card (pass `--effort` only to cross-check; a mismatch aborts). Add `--subdir <topic-slug> --step <N>` for sub-plans (see [sub-plans.md](./references/sub-plans.md)).

The script verifies the confirmed card, creates the deterministic structure in `docs/plans/`, **pre-fills** the plan's *Context and motivation* and *Non-goals* sections from the card, then **deletes the card** — from that moment the plan file is the single source of truth. It prints the path of the file to edit and regenerates `_index.md` automatically. If the design phase changed the effort agreed at the gate, get the user's explicit re-confirmation of the new effort, scaffold with the card's original effort, then update the plan frontmatter to the re-confirmed value and record the deviation in the plan's *Decisions* section.

Do not manually create files or folders in `docs/plans/`: the structure is the script's responsibility, not yours. This applies to sub-plans as well — see [sub-plans.md](./references/sub-plans.md).

---

### Step 3 — **Writing/editing content**:

Open the file returned by the script and fill in the sections following the conventions below.

## Index: generated, not hand-written

`create_plan.py` regenerates the index as part of scaffolding. After ANY other change to a plan file (content edit, status change, archive), you MUST run `uv run .claude/skills/write-plan/scripts/generate_index.py`. Never edit `_index.md` by hand.


## Frontmatter

```yaml
---
status: Draft | Reviewed | Implemented | Archived
effort: S | M | L | XL
---
```

| Status | Meaning | Who can set it |
|---|---|---|
| `Draft` | Being written, not ready for implementation | The agent, autonomously |
| `Reviewed` | Discussed and approved — ready for implementation | **The user only**, with explicit approval in chat |
| `Implemented` | Code completed | The agent, **only after** every DoD item is mechanically verified |
| `Archived` | Superseded or abandoned (indicate reason/replacement plan in the text) | The user, or the agent on explicit request |

**Non-negotiable rule**: the agent may never autonomously promote a plan from `Draft` to `Reviewed`. If asked to implement a plan still in `Draft`, stop and ask for explicit confirmation before proceeding — even if the plan "looks ready".


## Effort — Calibration

| Effort | Criterion |
|---|---|
| `S` | 1 file changed, less than 1h of estimated work |
| `M` | 2–4 files, half a day |
| `L` | 5+ files OR a data/schema migration; 1–3 days of estimated work |
| `XL` | Covers multiple distinct areas → **must be split into sub-plans — see [sub-plans.md](./references/sub-plans.md)**, not written as a single plan |


## Definition of Done

See [Template](./references/template.md).

### Note on tests in the plan

Tests listed under each step in `Draft` are **intent**, not an immutable contract. Real tests are generated by the `tdd-test-writer` agent (or another dedicated agent) and may legitimately diverge from what was written at planning time. If they diverge, **update the plan** instead of leaving it misaligned: a DoD that references non-existent tests is not verifiable, which violates this skill's guiding principle.

### Note on the DoD

The DoD is always the **last section** of the plan. Every item must be verifiable with a command (`grep`, `uv run pytest`, `python -c "import ..."`) — zero subjective criteria.

Do not copy the example variable block (e.g. `grep "OldSymbol"`) literally: it only makes sense for renames/refactors. For each plan, **generate items tailored to that plan's content**. The fixed block is always the same and must be left as-is.

## Mechanical Enforcement

The rules above do not enforce themselves. Use:

- **`uv run .claude/skills/write-plan/scripts/validate_plan.py <file>`** — validates filename, frontmatter (allowed fields, correct enum values), presence and position of the DoD, presence of the fixed block, and absence of code fences in the DoD.


## Archived Plans

`docs/plans/` accumulates noise over time if `Archived` plans remain mixed with active ones. `generate_index.py` (see [Index: generated, not hand-written](#index-generated-not-hand-written)) filters them automatically out of the main index view, grouping them in a separate section — do NOT physically move them to an `archive/` folder.

## Full Workflow

1. Write the plan with `status: Draft`, following the structure described in the sections above.
2. Run `uv run .claude/skills/write-plan/scripts/validate_plan.py <file>` **only after writing the content** — a freshly scaffolded file intentionally fails (empty sections). Fix until it passes.
3. The plan is reviewed → **the user only** explicitly approves → update to `status: Reviewed`.

## Updating an existing plan

1. After **any** edit to a plan file (content, status, wording), re-run `uv run .claude/skills/write-plan/scripts/validate_plan.py <file>` and re-run `uv run .claude/skills/write-plan/scripts/generate_index.py`.
2. Any substantive content change to a plan with `status: Reviewed` demotes it back to `Draft`; a new explicit user approval is required to return it to `Reviewed`. Typo and formatting fixes are excluded from this rule.
3. Status transitions always follow the permissions table above.

## Implementation Workflow

1. (Optional) Generate failing TDD tests (`tdd-test-writer` agent or manually). If they diverge from the tests described in the plan, update the plan.
2. Implement the plan (`python-developer` agent or manually).
3. Verify **mechanically** every DoD item — none ticked "by eye".
4. (Optional) Invoke the `doc-architect` agent (if available) to update the documentation.
5. Update the plan to `status: Implemented`.
