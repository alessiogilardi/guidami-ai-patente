<!--
SPEC — the contract. Durable, git-tracked, never deleted (superseded instead).
The user signs scope; the compiling skill asserts feasibility with codebase evidence.
Downstream plans are extracted from this document and reference FR ids: every
requirement must be individually testable and traceable.
Status lifecycle: draft → ready → in-progress → implemented → superseded.
Every status beyond draft is written by the user alone — skills only propose:
draft → ready at sign-off; ready → in-progress when the first plan is extracted;
in-progress → implemented once the Definition of Done is verified.
-->

# Spec 0021: On-demand glossary enrichment for the vocabulary explanation stage

| | |
|---|---|
| **Id** | 0021 |
| **Status** | draft |
| **Date** | 2026-09-25 |
| **Discussion log** | — (brainstormed inline via `superpowers:brainstorming`; no separate transcript file) |
| **Supersedes / superseded by** | — |
| **Extends** | Spec 0020 (unified "Spiega"): adds a second, independent source of glossary candidates inside the existing `_vocabulary_outcome` stage. Introduces no new endpoint. |
| **Enhanced by** | Spec 0019 (definition glossary): the DB-side candidate source this feature merges with, unchanged. |
| **Reuses** | Spec 0011/0012's live comma-retrieval infrastructure (`CandidateSetService` over `CorpusReadRepository`), read-only, for the on-demand agent's corpus grounding. |

## Problem & Motivation

`glossary_entries` (spec 0019) is only as complete as `build-glossary`'s offline
extraction pass has covered so far — it extracts verbatim term/definition pairs from
whichever corpus blocks are configured, one block at a time (ADR 0036, ADR 0038). A
quiz question can legitimately use a legal term the pass has not reached yet, or that
never appears as a standalone defined term in the corpus at all (e.g. "revoca",
"sospensione" — CdS uses both with precise, distinct legal meanings that a candidate
preparing for the exam needs to tell apart).

Today, when `GlossaryReadRepository.candidates_for` returns no good candidate for such
a term, `QuestionExplainerAgent` can still explain it — its own prompt already allows
"a term you explain from your own knowledge, with no matching candidate, in plain prose
without guillemets" — but that explanation gets no `«guillemet»` grounding marker, no
`translation_hints` entry, and therefore no dedicated glossary block (spec 0020, FR-8)
and no per-term Russian pinning on a later "Traduci" tap (spec 0018). The candidate
sees a lesser experience for exactly the terms most likely to be unfamiliar or newly
added to the corpus.

This spec adds a second, independent agent, `GlossaryEnricherAgent`, that generates its
own candidate definitions for a question's terms, live, on every explanation request —
grounded on the same corpus retrieval already used to ground the legal explanation
(answer-blind, no judge involved), falling back to the LLM's own general knowledge only
for a term that retrieval finds nothing for. Its output is merged with the DB-retrieved
candidates — the DB always wins a same-term conflict — before the merged list reaches
`QuestionExplainerAgent`, whose own contract does not change at all. The client can tell
which source grounded which cited term via a new `origin` field.

**Shapes considered and rejected during brainstorming, recorded so a future reader does
not re-propose them:**

- **Gap-detection via a retrieval-score threshold** before deciding whether to invoke
  the on-demand agent — rejected: introduces an arbitrary threshold/config knob on top
  of an already-fused RRF score, and does not remove the need to decide what "gap"
  means. Superseded by always running the on-demand agent and letting merge-with-
  DB-priority absorb the redundant case for free.
- **Gap-detection via an explicit expected-term extraction pass** (a separate step
  that lists the technical terms in the question, then checks each against
  `glossary_entries.term`) — rejected: adds its own LLM/heuristic call and a second
  point of failure *ahead of* the stage's own agent, for a problem the always-run
  approach avoids needing to solve at all.
- **`QuestionExplainerAgent` itself flagging missing terms**, then a follow-up call to
  fill them — rejected: a two-round-trip shape (flag, then generate) costs more
  latency than two independent sources gathered once, concurrently.
- **Write-through of on-demand definitions into `glossary_entries`** (mirroring the
  spec 0017 comma-labeling cache-fill pattern) — rejected: would mix verbatim
  corpus-extracted rows (ADR 0038's mechanical guarantee) with live-generated rows —
  sometimes grounded in a retrieved comma, sometimes from general knowledge — in the
  same table, with no reliable way to tell them apart on a later read. `build-glossary`
  stays the only writer of `glossary_entries`.
- **Reusing `GlossaryExtractorAgent` with its `output_validator` disabled by config**
  — rejected: that validator's verbatim-in-source-chunk contract (ADR 0038) is central
  to the class's identity; toggling it would blur two genuinely different tasks
  (extract-from-a-known-chunk vs. generate-from-live-retrieval-or-general-knowledge)
  into one class with two incompatible behaviors.
- **Conditional invocation** (only call the on-demand agent when DB retrieval looks
  weak) — rejected: reintroduces the gap-detection problem discarded above. Always
  running it in parallel is simpler and consistent with spec 0020's existing tolerance
  for an additional concurrent, best-effort stage.
- **Fuzzy or semantic dedup on merge** (e.g. embedding similarity between "sospensione"
  and "sospensione della patente") — rejected: introduces an arbitrary similarity
  threshold; normalized exact-match (`term.casefold()`) is simple, deterministic, and
  already the dedup key `ExplanationService._deduplicated_hints` uses today for a
  related case (two distinct DB rows sharing a term).
- **A per-question cache for on-demand entries** — not proposed by anyone and not
  considered: it would need the same write-through/provenance problem above just to
  exist, for a stage spec 0020 already established should be generated live and
  symmetrically with its DB-only sibling (spec 0020, AD-2).

## Functional Requirements

### FR-1: A second, independent agent generates glossary candidates, live, every call

`GlossaryEnricherAgent` (`agents/glossary_enricher/`, config
`configs/agents/glossary_enricher.yaml` — Italian output, unsuffixed per
`.claude/rules/agent-config-naming.md`) is invoked on every `GET .../explanation` call,
concurrently with `GlossaryReadRepository.candidates_for` (FR-3), never conditionally.
It receives the question's own `text` and `image_description` (answer-blind, mirroring
`QuestionExplainerRequest` — no `correct_answer`-derived field, structurally) and
returns a list of `{term, definition}` pairs, each written in the same simple Italian
register `question_explainer.yaml` already uses. It does not decide *whether* to run;
`ExplanationService` always calls it, and a genuinely term-free question yields an
empty list, which is a normal, non-error outcome.

### FR-2: Grounding reuses the existing legal-retrieval infrastructure, unchanged

Before generating, `GlossaryEnricherAgent`'s caller supplies it with the same
dense+full-text candidate commas `CandidateSetService`
(`labeling/services/candidate_set_service.py`) already retrieves to ground the legal
explanation — reached via `LiveLabelingStackProvider.candidate_set`
(`providers/live_labeling_stack_provider.py:81-83`), the identical instance
`CommaSelectorService` uses for live comma labeling. This retrieval is answer-blind by
construction: `CandidateSetService.execute` and the `CorpusReadRepository` methods it
calls (`dense_top_k`, `text_match_top_k`, `extract_lexemes`) take only an embedding and
lexemes, never `correct_answer` — only the comma-labeling *judge*, which this feature
never invokes, reads the answer. No new retrieval infrastructure is introduced; this
feature only adds a second caller of retrieval that already exists.

### FR-3: General knowledge is a fallback, never a competing source

The agent is instructed to ground a term's definition in the supplied candidate commas
whenever one of them supports it, and to fall back to its own general knowledge only
for a term no supplied comma addresses. This is a prompt-level instruction, mirroring
`question_explainer.yaml`'s own existing "explain from your own knowledge without
quoting" allowance — it is not mechanically enforced by an `output_validator`, the same
way that existing allowance is not.

### FR-4: On-demand entries are ephemeral — never written to `glossary_entries`

`GlossaryEnricherAgent`'s output is used to build the merged candidate list for the
current request only (FR-6) and is discarded afterward. Nothing in this feature ever
inserts a row into `glossary_entries`; the offline `build-glossary` pipeline (spec
0019) remains the table's only writer, keeping ADR 0038's verbatim guarantee meaningful
for every row the table holds.

### FR-5: The merged list is what `QuestionExplainerAgent` sees — its own contract is unchanged

`ExplanationService._vocabulary_outcome` builds one `list[GlossaryCandidate]` from
`GlossaryReadRepository.candidates_for` (unchanged call) and
`GlossaryEnricherAgent`'s output (mapped into `GlossaryCandidate`s, FR-6), shuffles it
exactly as today, and hands it to `QuestionExplainerAgent` inside the existing
`QuestionExplainerRequest.candidates` field. `QuestionExplainerAgent`,
`QuestionExplainerRequest` and `QuestionExplainerResponse` are not modified by this
spec: the agent still just cites ordinals from whatever list it is given.

### FR-6: Merge gives DB-retrieved candidates priority on a normalized-term conflict

A new pure function (`utils/`, per `.claude/rules/utils-package-placement.md` —
standalone, stateless, no injected dependency) merges the two sources:

- Every DB-retrieved `GlossaryCandidate` (`origin=DB`, the new enum default, FR-8) is
  kept as-is.
- Each on-demand `{term, definition}` pair becomes a `GlossaryCandidate` with
  `origin=AGENT_GENERATED` (FR-8), *unless* its `term.casefold()` already matches a
  DB-retrieved candidate's `term.casefold()`, in which case it is dropped — the DB
  entry, extracted verbatim from the corpus, wins.
- Two on-demand entries sharing a normalized term (the agent should not produce this,
  but nothing outside this function enforces it) are both kept; the pre-existing
  `_deduplicated_hints` dedup (keyed the same way, first-cited order) still applies
  downstream once `QuestionExplainerAgent` decides what to cite, unchanged.

### FR-7: A failure of the on-demand source degrades to DB-only candidates

`_vocabulary_outcome` runs the DB retrieval and the on-demand agent call concurrently
via `asyncio.gather(..., return_exceptions=True)` — not `asyncio.TaskGroup`, so one
side's failure does not cancel the other. If `GlossaryReadRepository.candidates_for`
raises, the whole vocabulary stage degrades to `(None, ())`, exactly as it does today
(unchanged). If only `GlossaryEnricherAgent` raises or exceeds its own share of the
stage's inner timeout, that failure is logged at `warning` and treated as an empty
on-demand list — the merge (FR-6) then trivially yields the DB-only candidates, and
`QuestionExplainerAgent` runs exactly as it does today without this feature. This
mirrors spec 0020's own principle (FR-5 there) that the vocabulary stage is additive,
best-effort value, applied one level deeper.

### FR-8: Provenance is surfaced per cited term in the API response

A new enum, `GlossaryTermOrigin` (`enums/`, `StrEnum`, members `DB` and
`AGENT_GENERATED`, values from `auto()`), is added to:

- `GlossaryCandidate` — new field `origin: GlossaryTermOrigin = GlossaryTermOrigin.DB`.
  The default keeps `GlossaryReadRepository._row_to_candidate`'s existing construction
  call unchanged; the merge function (FR-6) is the only caller that ever passes
  `AGENT_GENERATED`. This is a **new, distinct field from `GlossaryCandidate.source`**,
  which already exists and means the corpus source (`cds`/`cap`) — not provenance; the
  two are never confused.
- `CitedGlossaryTerm` (domain model) and `CitedGlossaryTermResponse` (API schema) —
  both gain `origin: GlossaryTermOrigin`, populated by
  `ExplanationService._deduplicated_hints` from the candidate's own `origin` field
  (`candidate.origin`), alongside the `term`/`definition`/`term_ru` it already copies.

```json
{
  "translation_hints": [
    { "term": "carreggiata", "definition": "…", "term_ru": "…", "origin": "db" },
    { "term": "revoca", "definition": "…", "term_ru": null, "origin": "agent_generated" }
  ]
}
```

No other part of `QuizExplanationResponse` changes. `origin` naming follows the
existing precedent of `ProvenanceResponse.origin` (comma-association provenance,
spec 0017) rather than reusing `source`.

## Non-Goals

- No new endpoint, no new request parameter on `GET .../explanation`.
- No gap-detection heuristic of any kind (score threshold, expected-term extraction) —
  the on-demand agent always runs (FR-1).
- No write-through of on-demand definitions to `glossary_entries`, ever (FR-4).
- No change to `GlossaryExtractorAgent`, `build-glossary`, or `translate-glossary-terms`.
- No change to `QuestionExplainerAgent`'s request/response contract (FR-5).
- No fuzzy/semantic dedup — normalized exact-match only (FR-6).
- No new retrieval infrastructure — grounding reuses `CandidateSetService`/
  `CorpusReadRepository` exactly as already wired for live comma labeling (FR-2).
- No bot-side (`guidami_ai_patente_bot`) change: the bot already renders
  `translation_hints` generically (spec 0020, FR-8); this spec only adds a field the
  bot is not required to render differently. Whether the bot should visually
  distinguish `agent_generated` hints is left to a future, separate decision.

## Architectural Decisions

### AD-1: Two independently-sourced glossary sets, merged before the writer agent sees them

Mirrors spec 0020's AD-1 shape (two independent producers, gathered concurrently, one
merged input) one level deeper: where spec 0020 gathers the *legal* and *vocabulary*
stages, this spec gathers the vocabulary stage's own two glossary sources *inside*
`_vocabulary_outcome`, before either reaches `QuestionExplainerAgent`. Keeping the
merge here, rather than teaching `QuestionExplainerAgent` about two sources, keeps that
agent's contract exactly what spec 0020 already tested and shipped.

### AD-2: Grounding reuses `LiveLabelingStackProvider.candidate_set`, not a new repository

`ExplanationService` gains `Autowired[LiveLabelingStackProvider]` (already a
`@provider` resolvable in this container, `providers/live_labeling_stack_provider.py`)
alongside its existing fields, and reads `.candidate_set` — the same
`CandidateSetService` instance `CommaSelectorService` already resolves through the same
provider for live comma labeling. No new pywire component, no new SQL: this feature's
only new database interaction is the LLM call itself. This choice trades a small
cross-cutting dependency (the vocabulary stage now touches a labeling-stack provider it
did not touch before) for zero new retrieval code to maintain and test — retrieval
correctness for `article_commas` stays proven by `CandidateSetService`'s and
`CorpusReadRepository`'s own existing tests.

### AD-3: `GlossaryEnricherAgent` is a new, distinct agent — not a reconfigured `GlossaryExtractorAgent`

Per the rejected-shapes discussion: `GlossaryExtractorAgent`'s verbatim
`output_validator` (ADR 0038) is not a switch to flip, it is the class's entire reason
to exist. `GlossaryEnricherAgent` gets its own config
(`configs/agents/glossary_enricher.yaml`, unsuffixed — Italian output, the project's
base language), its own request/response DTOs, and, if needed, its own duplicate-term
`model_validator` (mirroring `QuestionExplainerResponse._reject_repeated_ordinals`) —
independent of `GlossaryExtractorAgent` in every respect except sharing the general
"agent extracts/generates term+definition pairs" shape.

### AD-4: Ephemeral by design — `glossary_entries` keeps one writer

Choosing not to write on-demand entries through to `glossary_entries` (FR-4) is a
direct consequence of ADR 0038: a table whose rows are guaranteed verbatim-extracted
from a known corpus chunk cannot also hold rows generated live, sometimes from general
knowledge, without a provenance column of its own on that table — which would be a
schema change to a table this spec has no reason to touch. Ephemeral generation avoids
that decision entirely; if a future spec wants persistence, it is a separate, explicit
schema change with its own migration, not a side effect of this one.

### AD-5: Provenance field is new and separate from the existing `source` field

`GlossaryCandidate.source` already means the corpus source (`cds`/`cap`) — reusing that
name for retrieval-vs-generation provenance would silently overload it. `origin`
(`GlossaryTermOrigin`) is a new, independent field, named after the existing
`ProvenanceResponse.origin` precedent (spec 0017) rather than invented fresh.

### AD-6: Merge dedup key mirrors the existing `_deduplicated_hints` key

`term.casefold()`, DB priority. Keeping the same normalization as the pre-existing
downstream dedup (FR-6) means a reader only has to learn one term-equality rule for the
whole vocabulary stage, not two slightly different ones.

### AD-7: Partial degradation, scoped to exactly the on-demand agent's own failure

`asyncio.gather(..., return_exceptions=True)`, not `TaskGroup`, is a deliberate
departure from spec 0020's `_explain`-level use of `TaskGroup` (which *does* want a
sibling's failure to cancel the other, at that outer level). Here the two gathered
calls are independent value contributors to the *same* final list, and one existing
call (`GlossaryReadRepository.candidates_for`) already has its failure semantics fixed
by spec 0020 (degrade the whole stage) — this spec adds a second call whose failure
should degrade only its own contribution, which `TaskGroup`'s all-or-nothing
cancellation cannot express.

## Data Model

No new table, no new column on any existing table. All changes are Python-level:

- New `enums/glossary_term_origin.py`: `GlossaryTermOrigin(StrEnum)` — `DB`,
  `AGENT_GENERATED` (values via `auto()`, i.e. `"db"`, `"agent_generated"`).
- `models/glossary_candidate.py`: `GlossaryCandidate` gains
  `origin: GlossaryTermOrigin = GlossaryTermOrigin.DB`.
- `models/cited_glossary_term.py`: `CitedGlossaryTerm` gains
  `origin: GlossaryTermOrigin` (no default — always resolved explicitly from the
  candidate it was built from).
- `api/schemas/quiz_explanation.py`: `CitedGlossaryTermResponse` gains
  `origin: GlossaryTermOrigin`.
- New `agents/glossary_enricher/` package: `GlossaryEnricherAgent`,
  `GlossaryEnricherRequest` (question `text`, `image_description`, the retrieved
  candidate commas), `GlossaryEnricherResponse` (a list of `{term, definition}`
  entries — response DTO, Italian docstring/`Field(description=...)` per the
  code-conventions exception for agent response DTOs).
- New `configs/agents/glossary_enricher.yaml`.
- New merge function, `utils/glossary/merge_glossary_candidates.py` (exact path/name
  left to implementation, following the precedent of `comma_repeal_detector`/
  `chunking` cited in `.claude/rules/utils-package-placement.md`).
- `services/explanation_service.py`: `ExplanationService` gains
  `enricher: Autowired[GlossaryEnricherAgent]` and
  `labeling_stack: Autowired[LiveLabelingStackProvider]` (AD-2); `_vocabulary_outcome`
  is restructured per FR-2/FR-6/FR-7.

`GlossaryCandidate`'s `id: int`, `source: str`, `article_number: str`,
`comma_number: str` fields are all non-optional today and none of them are read
downstream past `_deduplicated_hints` (only `term`/`definition`/`term_ru`/`origin`
are copied into `CitedGlossaryTerm`). For an `AGENT_GENERATED` candidate, which has no
real `glossary_entries` row, these four fields are populated with placeholder values
(exact scheme — e.g. a negative synthetic `id` sequence, a sentinel string for
`source`/`article_number`/`comma_number` — left to implementation; see Open
Questions). `term_ru` is always `None` for an `AGENT_GENERATED` candidate: this feature
generates Italian only, exactly like `GlossaryExtractorAgent` does before
`translate-glossary-terms` runs its own separate pass (spec 0019, AD-11).

## Constraints

- pywire field injection throughout (`.claude/rules/pywire-di.md`): the new agent, and
  `ExplanationService`'s two new `Autowired` fields.
- Router body stays a thin controller: no route changes at all (FR-1's field addition
  is served by the existing route unchanged).
- One class per file; the new enum lives in `enums/`, never in `models/`
  (`.claude/rules/code-conventions.md`); the merge function lives in `utils/`, never
  `services/` (`.claude/rules/utils-package-placement.md`) — it has no injected
  dependency.
- Agent config file unsuffixed (Italian, base language,
  `.claude/rules/agent-config-naming.md`).
- Response DTO (`GlossaryEnricherResponse`) docstring and `Field(description=...)` in
  Italian, per the agent-response-DTO exception in `.claude/rules/code-conventions.md`;
  its request DTO stays English.
- No `continue` in loops; lazy `%s`/`%r` logging arguments, levels used purposefully
  (`.claude/rules/logging.md`).
- Tests in `tests/` mirroring `src/`, no `__init__.py`, pytest, TDD.

## Testing

- **Agent-level** (`GlossaryEnricherAgent`, mirroring `question_explainer`'s test
  shape): grounds a definition in a supplied candidate comma when one is relevant;
  falls back to general knowledge, still producing an entry, when no supplied comma is
  relevant to a given term; a duplicate `term.casefold()` within one response is
  rejected (if a `model_validator` is added per AD-3) or otherwise documented as
  tolerated — confirmed during implementation.
- **Merge function** (unit, pure, no fakes needed): a DB candidate and an on-demand
  entry sharing a normalized term — the on-demand one is dropped, the DB one keeps
  `origin=DB`; a non-conflicting on-demand entry is kept with `origin=AGENT_GENERATED`;
  an empty on-demand list returns the DB list unchanged; case/whitespace variants of
  the same term are still recognized as a conflict (`term.casefold()`).
- **`ExplanationService._vocabulary_outcome`** (unit, fakes): (a) both sources succeed
  — the merged, shuffled list reaches `QuestionExplainerAgent` and a cited
  `AGENT_GENERATED` term surfaces with the right `origin` in the result; (b) the
  on-demand agent raises or times out — the stage still returns a non-`None`
  `term_explanation` built from DB-only candidates, unchanged from spec 0020's current
  behavior; (c) `GlossaryReadRepository.candidates_for` raises — the whole stage still
  degrades to `(None, ())`, exactly as today (regression guard: this spec must not
  change this existing behavior).
- **Endpoint** (`api_client`, fake agents): `GET .../explanation` response's
  `translation_hints` entries carry the correct `origin` for a DB-sourced and an
  agent-generated hint in the same response.
- **`GlossaryCandidate`/`CitedGlossaryTerm` construction**: existing
  `GlossaryReadRepository._row_to_candidate` call sites still produce `origin=DB`
  without being touched (default-value regression guard).

## Feasibility Evidence

Verified 2026-09-25 on branch `feat/backend`.

- **FR-1/FR-5/AD-1** — `agents/question_explainer/question_explainer_agent.py:1-66`,
  `agents/question_explainer/dto/question_explainer_request.py:1-51`,
  `agents/question_explainer/dto/question_explainer_response.py:1-38` (the unchanged
  contract this spec's merged candidate list feeds into).
- **FR-2/AD-2** — `services/comma_selector_service.py:56-127` (`CommaSelectorService`
  already resolving `LiveLabelingStackProvider` and reading `.corpus`/labeling
  collaborators through it, the pattern this spec's `ExplanationService` addition
  mirrors); `providers/live_labeling_stack_provider.py:55-96` (`.corpus:
  CorpusReadRepository`, `.candidate_set: CandidateSetService`, both built once in
  `__init__`); `labeling/services/candidate_set_service.py:1-51`
  (`CandidateSetService.execute`, dense+text union, no `correct_answer` anywhere in its
  signature or body); `commons/repositories/db/corpus_read_repository.py:103-144,225-252`
  (`dense_top_k`, `text_match_top_k`, `extract_lexemes` — confirmed answer-blind,
  parameterized only by embedding/lexemes/`k`).
- **FR-4/AD-3/AD-4** — glossary extraction verbatim contract, quoted from
  `docs/second-brain/adr/0038-glossary-extraction-mechanical-verbatim-and-chunking.md:38-45`
  via the `second-brain:second-brain-reader` subagent this session dispatched; ADR 0036
  ("glossary is a new, independently-owned derived table") from the same dispatch.
- **FR-6/AD-6** — `services/explanation_service.py:250-277`
  (`_deduplicated_hints`, the existing `term.casefold()` dedup key and first-cited-order
  behavior this spec's merge step is written to stay consistent with).
- **FR-7/AD-7** — `services/explanation_service.py:192-248` (`_vocabulary_outcome`'s
  current single-`try` shape, the one inner `asyncio.timeout`, and the class docstring
  at `services/explanation_service.py:80-97` explaining why `TaskGroup` is used one
  level up in `_explain` but not appropriate for this spec's two independent,
  same-stage calls).
- **FR-8/AD-5** — `models/glossary_candidate.py:1-20` (confirmed `source` already means
  CdS/CAP, not provenance); `api/schemas/quiz_explanation.py:25-53`
  (`ProvenanceResponse.origin`, the naming precedent this spec's new field follows;
  `CitedGlossaryTermResponse`'s current shape, `term`/`definition`/`term_ru` only).
- **Constraints** — `.claude/rules/pywire-di.md` (`@provider`/`Autowired` conventions);
  `.claude/rules/agent-config-naming.md` (unsuffixed = Italian/base language);
  `.claude/rules/utils-package-placement.md` (merge function's placement);
  `.claude/rules/code-conventions.md` (enums in `enums/`; response-DTO Italian
  exception).
- **Spec 0020 precedent** —
  `docs/superpowers/specs/2026-09-21-question-explanation-design.md` (AD-1, AD-8,
  FR-5, the shapes this spec's AD-1/AD-7/FR-7 explicitly mirror or deliberately
  depart from, with the departure justified in each case).

## Open Questions

- [ ] **non-blocking** — Exact adaptation needed to call `CandidateSetService.execute`
  from `ExplanationService`: it takes a `QuizEvaluationRow`
  (`domain.models.retrieval.QuizEvaluationRow`), an evaluation-harness domain model.
  Whether `_vocabulary_outcome` constructs a minimal instance inline, or a narrower
  request shape is introduced, is left to implementation to confirm against that
  model's actual required fields.
- [ ] **non-blocking** — Placeholder scheme for `AGENT_GENERATED` `GlossaryCandidate`'s
  non-optional `id`/`source`/`article_number`/`comma_number` fields (proposed: a
  negative synthetic `id` sequence, a sentinel string for the other three) — confirm
  nothing downstream ever inspects these fields for such a candidate before finalizing.
- [ ] **non-blocking** — Whether `GlossaryEnricherResponse` needs its own
  `model_validator` rejecting a duplicate `term.casefold()` within one response
  (mirroring `QuestionExplainerResponse._reject_repeated_ordinals`) — recommended,
  confirm during implementation.
- [ ] **non-blocking** — Retrieval depths for the grounding call: reuse
  `LabelingConfig`'s existing `dense_k`/`text_k` (via the shared `candidate_set`
  instance, AD-2) or introduce separate ones tuned for this use — left to
  implementation; reusing the shared instance's own depths is the simpler default.
- [ ] **non-blocking** — Exact prompt text for `GlossaryEnricherAgent` (how many terms
  to surface per question, how strongly to prefer corpus grounding, register) and its
  model/config (proposed: same `openrouter/google/gemini-2.5-flash` as its siblings) —
  left to implementation, tuned on real output.
- [ ] **non-blocking** — Whether the bot should visually distinguish an
  `agent_generated` hint from a `db` one in the rendered glossary block (spec 0020,
  FR-8) — out of this spec's scope (Non-Goals); left to a future, separate decision if
  the plain-text distinction ever matters to a user.

## Follow-ups after implementation

- Run `second-brain:update` (`architecture.md`, `patterns.md`) to record: the
  two-source merge-with-priority pattern for a live LLM stage combined with a
  precomputed table, and `ExplanationService`'s new dependency on
  `LiveLabelingStackProvider` for read-only retrieval reuse outside the labeling flow
  itself.
- Record an ADR (`second-brain:adr`) for: generating supplementary glossary candidates
  live and merging them with DB priority instead of gap-detection-then-fill, and for
  keeping them ephemeral rather than write-through, given `glossary_entries`' verbatim
  contract (ADR 0038).
- Update the `CLAUDE.md` API endpoints table's description of `GET
  /{number}/explanation` to mention `translation_hints[].origin`.

## Sign-off

- **Scope approved by user:** pending — spec written 2026-09-25 from an interactive
  `superpowers:brainstorming` session; awaiting the user's review of this file.
- **Feasibility asserted:** by the assistant on 2026-09-25, based on the Feasibility
  Evidence above (direct source reads plus one `second-brain:second-brain-reader`
  dispatch for glossary-system ADRs).
- **Definition of Done verified:** not yet — pending implementation.

## Changelog

- **2026-09-25** — Initial draft, from an interactive `superpowers:brainstorming`
  session (detection-mechanism, grounding, trigger, write-through, new-agent,
  dedup-key, retrieval-reuse and provenance-granularity decisions all made
  conversationally, one question at a time, per this project's CLAUDE.md override of
  brainstorming's default batching).
