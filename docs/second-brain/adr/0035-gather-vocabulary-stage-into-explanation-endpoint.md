# ADR 0035: Gather the vocabulary explanation as a second, independent LLM stage inside the existing explanation endpoint

## Status

Accepted

## Context

`GET /quiz-questions/{number}/explanation` (spec 0017) rendered exactly one LLM
call — the legal explanation, via `ExplanationWriterAgent`, bounded by
`AppConfig.explanation_deadline_s`. Spec 0020 added a second capability: an
answer-blind explanation of the question's own wording and technical terms
(`QuestionExplainerAgent`, grounded on the new `glossary_entries` table via
`GlossaryReadRepository`), meant to render alongside the legal explanation in the
same bot message (three sections: vocabulary prose, legal prose, a glossary block).

The two stages are genuinely independent: the vocabulary stage never needs the
legal stage's result (or the answer at all — it is deliberately answer-blind, AD-4),
and the legal stage never needs the vocabulary stage's result. But a bug in the new,
additive vocabulary stage must never be able to degrade or take down the already-
shipped, already-live legal-explanation path.

## Decision

`ExplanationService._explain` splits into `_legal_outcome` (the unchanged spec-0017
path) and `_vocabulary_outcome` (new), run concurrently via `asyncio.TaskGroup`, both
still bounded by the single existing `explanation_deadline_s` timeout
(`src/guidami_ai_patente/services/explanation_service.py`). Four properties are
load-bearing:

1. **Gathered, not sequenced** — wall-clock latency is `max(legal, vocabulary)`, not
   their sum.
2. **One shared deadline, not two independent budgets** — the endpoint's worst-case
   latency contract to callers is unchanged by adding a second LLM call.
   `_vocabulary_outcome` additionally bounds its own work with a smaller inner
   `asyncio.timeout` (`explanation_deadline_s` minus a fixed margin,
   `_VOCABULARY_DEADLINE_MARGIN_S`), so a slow vocabulary call degrades on its own
   budget instead of being the thing that fires the shared *outer* deadline and 503s
   the legal stage too, even when the legal stage itself was fast.
3. **`_vocabulary_outcome` never raises out of itself** — its entire body (the DB read
   via `QuizQuestionRepository.find_question_vocabulary_context`, the retrieval call
   via `GlossaryReadRepository.candidates_for`, the `QuestionExplainerAgent.run` call,
   *and* resolving `cited_term_numbers` into `CitedGlossaryTerm`s) sits inside one
   blanket `try/except Exception`, degrading to `(None, ())` and logging a `warning`
   on any failure — including a `ValidationError` from a malformed glossary row (a
   `term` over `CitedGlossaryTerm`'s 80-char `max_length`, or blank; neither is
   enforced at the DB layer) and a `TimeoutError` from the inner timeout in point 2.
   This construction was originally placed *after* the `try/except`, which meant a
   malformed glossary row could crash the whole request past this boundary — a real
   bug in the first cut of this design, fixed as part of the final whole-branch
   review, not a hypothetical risk.
4. **`TaskGroup`, not `asyncio.gather`** — `asyncio.gather` does not cancel a sibling
   task merely because another awaited coroutine raised; only external cancellation of
   the `gather()` call itself propagates to its children. Since `_legal_outcome` can
   raise (`ExplanationUnavailableError`, via `_call_writer`) while `_vocabulary_outcome`
   never does, a legal-stage failure under `gather` left the vocabulary task running as
   an orphaned coroutine — wasting an in-flight LLM call — past the point `execute`
   had already handled the deadline. `asyncio.TaskGroup` cancels every other task in
   the group the moment one of them raises, so a legal-stage failure now genuinely
   interrupts an in-flight vocabulary call. The trade-off: `TaskGroup` wraps a child's
   exception in an `ExceptionGroup`/`BaseExceptionGroup` even when there is exactly one
   (Python 3.11+ semantics), so `_explain` unwraps it back to the single underlying
   exception before propagating, to keep `execute`'s `except TimeoutError` and every
   caller's `except ExplanationUnavailableError` working unchanged.

A further, related decision: candidates from `GlossaryReadRepository` (RRF-ordered) are
shuffled once (`random.shuffle`, no fixed seed) before being shown to
`QuestionExplainerAgent`, and the same shuffled list object is reused afterward to
resolve `cited_term_numbers` ordinals back into `CitedGlossaryTerm`s — never re-fetched
or independently re-shuffled, or the ordinals would silently resolve to the wrong
terms. Resolution also deduplicates by `term.casefold()` (first-cited order kept):
`glossary_entries` is unique on `(source, article_number, comma_number, term)`, so two
distinct rows can legitimately share a `term`, and citing both would otherwise produce
duplicate `translation_hints` — rejected with a `422` by
`ExplanationTranslationRequest`'s wire-layer validator, permanently breaking "Traduci"
for that question (fixed in the same final-review pass as points 3 and 4 above).

## Alternatives considered

- **A separate new endpoint** (e.g. `GET /quiz-questions/{number}/vocabulary`) instead
  of extending the existing explanation response. Rejected — the bot's own rendering
  wants both sections composed into one message; a separate endpoint would force the
  bot into two round trips with independent timeout/failure handling just to render
  one screen, and would duplicate the answer-lookup plumbing `_explain` already does
  once.
- **Sequence the two stages** (legal, then vocabulary) instead of gathering them.
  Rejected — the two calls share no data dependency, so sequencing would only add
  latency (their sum instead of their max) for no correctness benefit.
- **Give the vocabulary stage its own, independent (caller-visible) deadline** —
  a second timeout the endpoint's total worst-case latency would grow to accommodate.
  Rejected — that would silently widen the contract every caller of `/explanation`
  already depends on. The inner `asyncio.timeout` point 2 of the Decision actually
  uses is a different thing: a *strictly narrower* sub-budget nested inside the
  existing `explanation_deadline_s`, never widening the total. Its purpose is not to
  give the vocabulary stage more room — it's to make sure a slow vocabulary call
  degrades on its own before it could otherwise be the specific thing that trips the
  shared outer deadline and turns into a 503 for the legal stage too.
- **Let a vocabulary-stage failure propagate** (matching how a legal-stage failure
  becomes a 503 via `ExplanationUnavailableError`) instead of degrading silently.
  Rejected — the vocabulary stage is additive; a caller that already worked before
  spec 0020 must keep working identically if the new stage misbehaves, so failure
  there degrades the response, it does not fail the request.

## Consequences

Adding a second LLM stage costs no additional worst-case latency budget and cannot
regress the existing legal-explanation guarantee — verified both by task review
(tracing the `try/except` boundary against every call inside `_vocabulary_outcome`)
and by a real-model smoke test showing a legal-stage refusal (`insufficient_knowledge`)
still carrying a real, independently-computed vocabulary explanation.

The cost: the vocabulary stage's *failure* mode is invisible to the API response — a
caller cannot distinguish "the vocabulary agent errored" from "the DB read failed"
from "the inner timeout expired" from the response alone; all of them take the one
degrade path (point 3 of the Decision) to `term_explanation: null`, `translation_hints:
[]`, with the specific cause visible only in the `warning` log line, never surfaced to
the client. This is *not* the same as "no glossary term applied to this question" — an
empty or non-matching candidate retrieval is not a failure at all: `QuestionExplainerRequest.candidates`
may legitimately be empty (FR-4/FR-6), the agent still runs, and `term_explanation` comes
back as a real, non-null sentence with `translation_hints: ()` (confirmed live by the
Task 11 smoke test's clean no-match case). `null` only ever means a genuine failure
happened, never "nothing to say." If per-failure-cause visibility becomes a real product
need later, that is a new, separate decision (a status field on the response, or
similar), not implied by this one.

**Note (spec 0021, added 2026-09-26, first grilling round finding)**: the vocabulary
stage's answer-blindness (AD-4 above) was originally adopted as a testability
convention, mirroring the already-answer-blind `RoadSignDescriberAgent` (ADR 0001), not
as a genuine privacy/leakage boundary. `GET .../explanation` is reachable only
post-answer — the caller has already submitted and seen the verdict via
`POST .../check` before this endpoint is ever called — so there is no actual
information being protected by keeping `_vocabulary_outcome`/`QuestionExplainerAgent`
(and, since spec 0021, `GlossaryEnricherAgent`) from seeing `correct_answer` at the
API-contract level. It is kept anyway for architectural consistency with the sibling
agent and to keep the vocabulary stage decoupled from grading logic — not because
leaking the answer here would be a real problem. This does not change the Decision
above; it only corrects the rationale a future reader might otherwise assume.
