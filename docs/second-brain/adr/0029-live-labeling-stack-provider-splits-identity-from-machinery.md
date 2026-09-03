# ADR 0029: The Shared Labeling Stack Is Assembled by Three Providers, Amending AD-16

## Status

Proposed

## Context

Spec 0012's AD-16 (`docs/superpowers/specs/2026-08-24-quiz-flow-api-design.md`)
established that code shared with the pre-`pywire` world (`commons/`, `labeling/`,
third-party classes) is built inside a `@provider`'s own `__init__`, and consolidated
what would otherwise be seven near-identical per-class wrappers into **two**
providers: `PostgresClientProvider` for the connection pool, and a single
`LabelingStackProvider` for everything else the judge needs — the agent, the
retrieval collaborators, the tracker.

`LabelingStackProvider` already exists and is resolved on **every** `POST
/quiz-questions/{number}/check` request, through `ExplanationStatusService`
(spec 0013 FR-4), to read `LabelingStackProvider.epoch` for FR-8's precedence
query. It is also resolved by `_run_judge_coherence_check` at startup (FR-14), a
diagnostic that deliberately wraps its own resolution in `try/except Exception`
so a startup problem never aborts the process — a diagnostic must degrade to a
warning, not a boot failure.

Building the live judge's actual machinery — `CommaLabelerAgent`, the OpenRouter
model client, the LLM call tracker, the candidate-set/lexeme services, the
golden-set write repository — requires spec 0012 phase 3's `QuestionLabelingService`
(ADR 0030) plus everything it depends on. If `LabelingStackProvider` built all of
that itself, as AD-16's original "two providers total" called for, two problems
follow directly from the two facts above:

1. **The FR-14 startup diagnostic's swallowing `except Exception` would also
   swallow a malformed prompt file or a bad OpenRouter credential**, because
   resolving the epoch would now also construct the whole LLM graph — a
   configuration error that should abort a deployment or surface loudly would
   instead read as one warning log line about "the judge coherence check
   failed", indistinguishable from a transient DB hiccup.
2. **Every `POST /check` request would build an LLM graph it never calls.**
   `ExplanationStatusService` only ever reads `epoch`; it never labels anything.
   Constructing `CommaLabelerAgent`/`OpenRouterProvider`/the tracker on a path
   that measurably never uses them is wasted work on the API's hottest route.

This is quiz-flow-api-phase3 plan decision D3, implemented in Task 9
(`LiveLabelingStackProvider`) and recorded as a spec errata against AD-16 in
Task 14 (`docs/superpowers/specs/2026-08-24-quiz-flow-api-design.md`, the
2026-09-02 errata on AD-16).

## Decision

Split the machinery out of `LabelingStackProvider` into a new, second provider,
`LiveLabelingStackProvider` (`guidami_ai_patente/providers/live_labeling_stack_provider.py`).
The shared labeling stack is now assembled by **three** providers, not two:

- `PostgresClientProvider` (`guidami_ai_patente/clients/postgres_client_provider.py`)
  — the connection pool, unchanged from AD-16/ADR 0017.
- `LabelingStackProvider` — stays the judge's **identity** only: `agent_config`
  (the loaded `comma_labeler.yaml`) and the `LabelingEpoch` derived from it.
  Nothing here constructs an LLM client or an agent.
- `LiveLabelingStackProvider` — the **machinery**: `Autowired[AppConfig,
  LabelingConfig, LabelingStackProvider, PostgresClientProvider,
  OpenRouterProviderComponent, LlmCallTrackerProvider]`, built once, exposing
  `corpus`/`quiz`/`golden_set`/`candidate_set`/`question_labeling` as plain
  attributes. The judge it builds comes from `LabelingStackProvider.agent_config`
  — the already-loaded prompt whose hash is the epoch's `prompt_version` — never
  reloaded, so this provider cannot silently diverge from the identity
  provider's epoch.

Two more providers complete the picture, both pre-existing infrastructure this
ADR does not change but that `LiveLabelingStackProvider` depends on:
`OpenRouterProviderComponent` (the one shared `OpenRouterProvider`, third-party,
AD-16 rule 2) and `LlmCallTrackerProvider` (ADR 0031, D5). The dependency edge on
`LlmCallTrackerProvider` is load-bearing, not incidental: `Container.close()`
runs `@pre_destroy` hooks in reverse build order, and `LiveLabelingStackProvider`
depending on it is what keeps the tracker's queue draining before the pool it
writes through closes.

`CommaSelectorService` (the only consumer that needs the machinery) autowires
both `LabelingStackProvider` (for `epoch`) and `LiveLabelingStackProvider` (for
`question_labeling`, `quiz.find_with_vector`, `golden_set.find_or_create_live_run`).
`ExplanationStatusService` and the FR-14 startup check autowire only
`LabelingStackProvider`.

## Alternatives considered

- **Keep AD-16's original "two providers total"** (this ADR's rejected
  status quo) — the two failure modes in Context are the reason it is
  rejected: an eager-construction diagnostic hazard and unconditional LLM-graph
  construction on the hot no-LLM path.
- **One provider per shared class** (the seven-wrapper shape AD-16 already
  rejected once) — rejected again for the same reason: mechanically uniform,
  but seven near-identical wrappers for a graph the extracted `labeling.wiring`
  builders already know how to assemble in one place. Splitting identity from
  machinery is two providers with genuinely distinct responsibilities, not a
  regression to the per-class shape AD-16 moved away from.
- **A lazy/cached property on `LabelingStackProvider`** that builds the
  machinery on first access rather than eagerly in `__init__` — would still let
  the *first* `POST /check` after startup pay the construction cost (and, worse,
  make that cost non-deterministic across requests depending on ordering),
  without solving the FR-14 diagnostic-masking problem at all, since the
  diagnostic resolves the provider regardless of which properties it later
  touches.

## Consequences

- Spec 0012's AD-16 no longer accurately describes the provider count; the
  spec carries a dated errata (2026-09-02) recording the amendment rather than
  being silently rewritten, per this repo's append-only errata convention.
- `POST /check` never constructs an LLM client, an agent, or a tracker; only
  `GET /quiz-questions/{number}/explanation` (via `CommaSelectorService`) does.
- The FR-14 startup diagnostic's `except Exception` now only ever swallows a
  genuine coherence-check failure (a DB read), never a prompt-file or
  credential problem — those now fail where they are actually used, on
  `LiveLabelingStackProvider`'s own construction.
- One more provider to reason about, and one more `Autowired` edge
  (`LiveLabelingStackProvider` → `LlmCallTrackerProvider`) whose removal would
  silently break shutdown ordering — flagged in both providers' docstrings so a
  future edit does not drop it by accident.
