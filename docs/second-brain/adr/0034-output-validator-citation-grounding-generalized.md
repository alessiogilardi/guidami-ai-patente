# ADR 0034: Citation-grounding retries live in each agent's own `output_validator`, not in the calling service

## Status

Accepted

## Context

`ExplanationService._call_writer` used to range-check `ExplanationWriterAgent`'s
`cited_comma_numbers` after the fact and, on an out-of-range ordinal, re-issue the
whole `ExplanationWriterAgent.run` call up to `_CITATION_ATTEMPTS = 3` times — a
service-level manual retry loop, separate from and unaware of pydantic-ai's own
retry machinery.

`CommaLabelerAgent` (spec 0014) had already solved the identical problem
differently: it registers its own `pydantic_ai.Agent.output_validator`, which reads
the original request off `ctx.deps` (threaded by `BaseAgent.run`/`run_sync`), bound-
checks the cited ordinals, and raises `pydantic_ai.ModelRetry` (Italian — prompt-
facing feedback the model reads mid-conversation) on an out-of-range value. This
lets the model self-correct within pydantic-ai's own retry budget
(`config.num_retries`) instead of the caller re-issuing a fresh call from scratch.

Spec 0020 needed a second citation-grounded agent (`QuestionExplainerAgent`, citing
into a `GlossaryReadRepository` candidate list rather than a comma list) and used
this as the occasion to also migrate `ExplanationWriterAgent` off its old service-
level loop and onto the same shape (`src/guidami_ai_patente/agents/
explanation_writer/explanation_writer_agent.py`, `src/guidami_ai_patente/agents/
question_explainer/question_explainer_agent.py`).

## Decision

Every agent whose output cites into a caller-supplied candidate list (commas,
glossary candidates, or any future list) owns its own ordinal-range enforcement via
a `pydantic_ai.Agent.output_validator` registered in its `__init__`, reading the
bound list's length off `ctx.deps` and raising `ModelRetry` (Italian) on an out-of-
range ordinal — reusing pydantic-ai's `num_retries` budget. The calling service
never range-checks or retries citations itself: it calls the agent once and maps
any exception the agent still raises (including `UnexpectedModelBehavior` once the
agent's own retry budget is exhausted) to its own failure response.

## Alternatives considered

- **Keep the service-level manual retry loop** (what `ExplanationService._call_writer`
  did before this branch): re-issue the whole LLM call up to N times, checking the
  response afterward. Rejected — it re-runs the entire call (system + user prompt,
  full generation) on every retry instead of an in-conversation nudge, it duplicates
  logic `CommaLabelerAgent` already solved once, and it leaves the retry policy split
  across two places (the service's attempt count, the agent's own YAML `num_retries`
  for structural validation failures) that could silently disagree.
- **A shared base-class method on `BaseAgent`** that every grounded agent inherits.
  Rejected for now — the bound-check target differs per agent (`len(ctx.deps.commas)`
  vs. `len(ctx.deps.candidates)`), and three occurrences is not yet enough repetition
  to justify a generic abstraction over "which field on `ctx.deps` holds the list";
  revisit if a fourth agent needs the identical shape with no per-agent variation.

## Consequences

Each grounded agent is now correct-by-construction for citation ordinals: a service
consuming it never needs to know the grounding mechanism exists, only that a raised
exception means "give up, don't render a fabricated citation." This is cheaper per
retry (an in-conversation `ModelRetry` vs. a fresh call) and removes one class of
service/agent drift (a service tuning its own attempt count independently of the
agent's actual retry budget).

The cost: there is no longer one place in the service layer to see or tune the
citation-grounding retry policy across every agent — it is now three sites (one
`output_validator` per agent, sharing no code), each with its own `num_retries` in
its own YAML config. A future policy change (e.g. "always allow 5 retries for
citation grounding specifically, distinct from structural-validation retries") would
need to be applied at each agent individually, or would motivate revisiting the
rejected shared-base-class alternative above.
