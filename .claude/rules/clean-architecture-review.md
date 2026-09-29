# Specs and plans — always consult `clean-architecture`

Whenever a **spec** (`docs/superpowers/specs/`) or an **implementation plan**
(`docs/superpowers/plans/`) is written or materially revised, invoke the
`clean-architecture` skill (`skill: "clean-architecture"`) and check the draft
against it before presenting it for approval.

**Why:** a spec or plan fixes the structure (packages, boundaries, dependency
direction) long before any code exists; a violation caught there is a rewrite of a
paragraph, caught in code it is a refactor.

**How to apply:**
- Invoke the skill while drafting, not after sign-off. It complements — does not
  replace — `second-brain:read` (this project's own conventions and ADRs).
- Check at least: the Dependency Rule (dependencies point inward: `orchestrators/` →
  `services/` → `repositories/`/`clients/`, never the reverse), SOLID (especially SRP and
  DIP), cohesion/coupling of the new components, and where the boundaries are drawn
  (business logic out of API routes, I/O separated from domain logic).
- Record the outcome in the spec/plan itself: an Architectural Decision (AD) for each
  non-obvious boundary choice, and an explicit note for any deliberate deviation, with
  its trade-off. If the project's own conventions (`.claude/rules/`, ADRs) conflict with
  the skill, the project's conventions win — state the conflict rather than silently
  picking one.
- Applies to specs and plans alike, including amendments that add or move components;
  it does not apply to status-only or typo edits.
