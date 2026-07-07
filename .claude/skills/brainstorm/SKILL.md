---
name: brainstorm
description: Open a discovery conversation with the user to understand the context, scope, constraints, and effort of a task before any plan is written. Use when the user wants to think through, scope out, or clarify requirements for a feature/refactor/bug — "let's brainstorm X", "help me figure out what's needed for X", "before we plan this, let's talk through X". Always run before write-plan when no confirmed Understanding card file exists yet for the slug (docs/plans/.brainstorm/<slug>.md with confirmed true). Never writes plan files, never writes code — its only artifact is the Understanding card, written exclusively via its own create_card.py script and consumed by the write-plan skill next.
allowed-tools:
  - Read
  - Grep
  - Glob
  - AskUserQuestion
  - "Bash(git log:*)"
  - "Bash(git status:*)"
  - "Bash(git diff:*)"
  - "Bash(uv run .claude/skills/brainstorm/scripts/*)"
---

# Brainstorming

> This skill only discusses and clarifies. It never writes plan files and never writes code. Its only artifact is a confirmed **Understanding card** — Problem/Motivation, Non-Goals, Affected Areas, Success Criteria, Effort, and slug — persisted at `docs/plans/.brainstorm/<slug>.md` via `create_card.py` (the skill's only write path) and consumed by the `write-plan` skill next to run Approach Exploration, Design, and scaffolding. The card file survives session restarts, so planning can resume in a fresh conversation.

## Workflow

1. **Context exploration**: Read the relevant files, docs, and recent commits (`git log`, `git status`, `git diff`) to ground your questions in what actually exists — never ask the user something you can answer yourself by reading the code.
2. **Scope Assessment and Decomposition**: Assess the breadth of the request before asking anything. If it describes multiple independent subsystems (e.g. "build a platform with chat, file storage, billing, and analytics"), flag it immediately. Help the user decompose the work into independent sub-projects, defining relationships and development order. Each sub-project gets its own independent cycle (brainstorm → plan → implementation).
3. **Ask questions — one at a time, multiple choice**: Surface exactly one question per turn, using `AskUserQuestion` with multiple-choice options wherever possible. Wait for the answer before asking the next question — never batch several questions into one call, and never ask an open free-text question when a multiple-choice framing captures the real alternatives. Fall back to open-ended phrasing only when the space of answers can't be enumerated.
4. **Calibrate question volume to effort** (see table below) — estimate effort early so you know how much to ask, then reconfirm it at the gate once the picture is clear.
5. **Understanding card**: Once you have enough signal, present the fields below in a single chat message AND persist them by running:
   `uv run .claude/skills/brainstorm/scripts/create_card.py <slug> --effort <S|M|L|XL> --problem "..." --non-goals "..." --affected-areas "..." [--success-criteria "..."]`
   The card is written with `confirmed: false`. If the user asks for changes, re-run the same command — it overwrites an unconfirmed card.
6. **Blocking gate**: Get the user's explicit confirmation on *slug* and *effort*, then — and only then — run `uv run .claude/skills/brainstorm/scripts/create_card.py <slug> --confirm`. Never run `--confirm` without that explicit confirmation in chat: the gate is enforced mechanically — `write-plan`'s scaffolding script refuses to run without a confirmed card.
7. **Hand-off**: Once confirmed, tell the user brainstorming is complete and to invoke `/write-plan`, which consumes the card (approach exploration, design, scaffolding). Do not propose solutions, trade-offs, or designs yourself — that belongs to `write-plan`.

---

## Required Output: the Understanding Card

Every brainstorming session ends with these fields — presented in one chat message and persisted to `docs/plans/.brainstorm/<slug>.md` via `create_card.py`. They map directly to the future plan: Problem/Affected Areas/Success Criteria pre-fill *Context and motivation*, Non-Goals pre-fills *Non-goals*, Effort becomes the frontmatter.

* **Problem / Motivation**: The business value or bug to fix (extreme summary).
* **Non-Goals (Draft)**: What is explicitly excluded from this intervention.
* **Affected Areas**: Modules, files, or code components impacted.
* **Success Criteria** (mandatory for L/XL): Observable outcomes that define success.
* **Effort Estimate**: Proposed sizing (S, M, L, XL).

Alongside it, propose a plan *slug* (kebab-case, matching `write-plan`'s scaffolding conventions). When Scope Assessment decomposed the request into multiple sub-projects, produce one card file per sub-project, each with its own slug, and state the recommended development order in chat.

## Question Logic Proportional to Effort

Calibrate the depth of investigation to avoid unnecessary overhead — but regardless of effort, every question that *is* asked follows the one-at-a-time, multiple-choice rule above.

| Effort Level | Question Quantity | Required Actions and Focus |
| :--- | :--- | :--- |
| **S** | None (0) | Only propose the plan *slug* and effort *S*, asking only for confirmation to proceed. |
| **M** | Max 1 or 2 | Ask questions only if there are real ambiguities about affected code areas. One question per turn. |
| **L / XL** | Mandatory | Strategic questions to understand scope, constraints, and success criteria. Clarify *non-goals*, technical risks, critical dependencies, and potential breaking changes. One question per turn. |

## Blocking Gate (Non-Negotiable Rule)

**ABSOLUTE PROHIBITION**: Never propose approaches, designs, or trade-offs, and never suggest running any scaffolding command. This skill's scope ends at a confirmed slug + effort — everything past that point belongs to `write-plan`.

The model proposes the Understanding card and any necessary questions; the user unlocks the hand-off to `write-plan` by explicitly confirming slug and effort in chat. Only after that confirmation may `create_card.py <slug> --confirm` be run — the confirmed card file is what `write-plan`'s scaffolding checks for. Never run `--confirm` preemptively or "to save a step".
