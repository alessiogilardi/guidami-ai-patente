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

# Spec 0017: On-demand quiz explanation ("Spiega" button)

| | |
|---|---|
| **Id** | 0017 |
| **Status** | implemented |
| **Date** | 2026-09-18 |
| **Discussion log** | — (brainstormed inline via `superpowers:brainstorming`, no separate transcript file) |
| **Supersedes / superseded by** | — |

## Problem & Motivation

Today the Telegram bot always fetches and shows the explanation in the same
turn as the answer: `QuizFlowService.handle_answer` calls
`POST /check` and `GET /explanation` together, and the message rendered to
the user already contains both the grade and the explanation text
(`src/guidami_ai_patente_bot/services/quiz_flow_service.py:42-64`,
`src/guidami_ai_patente_bot/handlers/quiz_handlers.py:116-150`). This makes
the explanation mandatory reading and mandatory latency: a cache miss on
`/explanation` runs retrieval plus an LLM judge call before the user ever
sees whether they were right (`ExplanationService.execute`,
`src/guidami_ai_patente/services/explanation_service.py:71-95`).

This spec makes the explanation optional: the user sees the grade
immediately, and can tap a "Spiega" button to fetch the explanation only if
they want it. The message is then updated in place — the question and the
grade stay visible, the explanation is appended.

Reaching this design took several rejected intermediate shapes, discussed
and discarded during brainstorming (recorded here since they are the kind of
thing a future reader would otherwise re-propose):

- **Eager retrieval synchronously inside `/check`** — rejected: it would
  reintroduce exactly the LLM-graph construction on the "hot" deterministic
  check path that ADR 0029 deliberately keeps out
  (`src/guidami_ai_patente/providers/`, `docs/second-brain/architecture.md`
  per the `second-brain:second-brain-reader` lookup performed during
  brainstorming), and would make `/check`'s latency depend on a judge call.
- **Eager, fire-and-forget labeling triggered when the question is shown or
  right after `/check`, with an in-process task registry to deduplicate a
  concurrent button tap** — rejected as unnecessary complexity once the
  design moved to a single, sequential trigger point (the button tap
  itself); a background trigger buys latency-hiding at the cost of a real
  concurrency question (two invocations of the judge for the same question)
  that the sequential design avoids by construction.
- **A new `LABELING`/in-progress status surfaced to the client, requiring
  the bot to poll** — rejected: with the button tap doing `label` then
  `explanation` strictly in sequence and awaited, there is no
  caller-visible in-progress state to represent.

The design that survives is intentionally the simplest one: three endpoints,
each with one job, called in sequence only when the user asks for the
explanation.

## Functional Requirements

### FR-1: The bot shows a "Spiega" button after grading an answer, not the explanation itself

Given a graded answer, the bot's message shows the outcome (correct/wrong)
and an inline keyboard offering "Spiega" (fetch the explanation) and
"Prossima domanda ▶" (move on) — not the explanation text.

### FR-2: The button is omitted when there is nothing to explain

If `POST /check`'s `explanation_status` is `UNAVAILABLE`, only "Prossima
domanda ▶" is shown — tapping "Spiega" would always fail, so it is not
offered.

### FR-3: Tapping "Spiega" ensures the labeling, then renders the explanation, then edits the message in place

On tap, the bot first edits the message optimistically — before calling
anything — removing "Spiega" from the keyboard (keeping "Prossima domanda
▶") and appending a loading line ("⏳ Generando spiegazione...") to the
text/caption. It then calls, in sequence and awaited: `POST
/quiz-questions/{number}/label`, then `GET
/quiz-questions/{number}/explanation`. The message is edited a second time
to replace the loading line with the explanation (or the existing "no
explanation available" line on failure), keeping the keyboard at just
"Prossima domanda ▶" (already the state after the first edit).

"Prossima domanda ▶" is never disabled during this wait: the user may tap
it while the explanation is still loading for the previous question. The
in-flight `/label`→`/explanation` sequence still completes and performs its
final edit on that now-superseded message — harmless, since the user has
already moved on and the edit has no effect on the new question's flow.

### FR-4: `POST /quiz-questions/{number}/label` ensures a current comma labeling exists

New endpoint, returning `204 No Content` on success. It computes a labeling
live (retrieval + judge + write) only if none is already current for the
question under the active epoch; otherwise it is a cache read with no
retrieval and no judge call (idempotent). It reuses the existing
`CommaSelectorService`
(`src/guidami_ai_patente/services/comma_selector_service.py:22-133`)
unchanged. It runs under its own explicit deadline (see AD-10); exceeding it
is a `503`, handled by the bot exactly like any other failure of this
endpoint (see AD-12).

### FR-5: `GET /quiz-questions/{number}/explanation` never triggers labeling

The endpoint's contract narrows: it renders an explanation strictly from an
**already-existing** current labeling. It no longer has a code path that
retrieves and judges on a miss. If no current labeling exists for a
question whose embedding **is** present (i.e. `/label` was skippable
by the caller, a contract violation in the intended flow), it fails
explicitly rather than silently computing the labeling itself (see AD-4).
The existing "insufficient knowledge" outcome (a labeling exists but the
judge found no supporting commas, or the question was never indexed at all)
is unchanged. Its own deadline shrinks accordingly, now covering only the
writer stage (see AD-11).

### FR-6: `POST /check`'s `explanation_status` reaches the bot

`QuizApiClient.check_answer` currently discards `explanation_status` from
the `/check` response body, returning only `correct`
(`src/guidami_ai_patente_bot/clients/quiz_api_client.py:58-68`). It must
return both, so `QuizFlowService`/the handler can decide whether to render
the "Spiega" button (FR-2).

## Non-Goals

- No eager or background labeling triggered by showing a question or by
  `/check` — rejected during brainstorming (see Problem & Motivation).
- No new "in progress" status exposed to any client of `/check` or
  `/explanation`.
- No protection against two *different* users tapping "Spiega" on the same
  unlabeled question at the same moment (a theoretical duplicate judge
  call) — the sequential, single-trigger-point design removes the
  *common* race (the same user's own eager-then-tap sequence); the
  cross-user case is accepted as out of scope for a personal-scale project,
  consistent with the "keep the design simple, even at some performance
  cost" priority already recorded in spec 0016.
- No change to `/quiz-questions/random`, `/quiz-questions/{number}`, or
  `/quiz-answers/summary`.
- No change to the golden-set schema or write path.

## Architectural Decisions

### AD-1: Three endpoints, each with one job — not two, and not one with an internal flag

`/check` (grade), `/label` (ensure labeling), `/explanation` (render text
from an existing labeling) each do exactly one thing. The alternative —
folding "ensure labeling" into `/explanation` as an internal fallback, as
it works today — was explicitly rejected by the user: `/explanation`'s only
job becomes rendering, never computing.

### AD-2: `/label` is a thin router wrapper over the existing `CommaSelectorService`

No new domain logic: `CommaSelectorService.execute` already is "serve the
cached comma association, or compute it live and write it through"
(`comma_selector_service.py:24-31`), which is exactly `/label`'s contract.

### AD-3: `ExplanationService` swaps `CommaSelectorService` for a new read-only `CurrentLabelingReadService`; `CommaSelectorService` is refactored to use it for its own hit branch

Today `ExplanationService.selector: Autowired[CommaSelectorService]`
(`explanation_service.py:68`) can trigger live labeling on a miss via
`CommaSelectorService.execute` → `_label_live`
(`comma_selector_service.py:53-67, 69-104`). Per FR-5, `ExplanationService`
must never do that. The read-only path already exists as
`CommaSelectorService`'s hit branch — `find_current_labeling` +
`_selection_for` (`comma_selector_service.py:63-66, 121-133`) — so it is
extracted into its own `@service` component, `CurrentLabelingReadService`
(named per `.claude/rules/code-conventions.md`'s `*Service` fallback — it
is a domain component with injected dependencies, not a repository or a
mapper; `CurrentLabelingRead` mirrors the existing `CurrentLabeling` domain
model and the `Read` prefix `GoldenSetReadRepository` already uses for the
same "no compute, only reads" distinction, making the read-only nature
explicit in the name rather than in the output shape alone), used by
**both** `CommaSelectorService` (hit branch) and `ExplanationService` (its
only path), instead of duplicating that logic in two places. This is the
single-responsibility split the user asked to note for future work (see
"Note for future work" below).

### AD-4: A current-labeling miss with an existing embedding is a new, explicit error from `/explanation`

`CurrentLabelingReadService` must distinguish two shapes of "no current labeling
found," mirroring the classification `ExplanationStatusService` already
performs (`explanation_status_service.py:32-51`):

- No embedding at all → unchanged behavior: the existing `not_indexed`
  "insufficient knowledge" outcome (`explanation_service.py:170-174`).
- Embedding present, no labeling → a genuine contract violation under this
  spec's intended flow (the caller should have called `/label` first). A
  new exception, `LabelingNotReadyError`, is raised and mapped to `409` by
  the app's exception-handler registration, alongside the existing
  `QuestionNotFoundError` (404) and `ExplanationUnavailableError` (503)
  mappings.

### AD-5: The bot always calls `/label` before `/explanation`, unconditionally

Even when the check-time `explanation_status` was already `CACHED`, the
"Spiega" tap still calls `/label` first. The extra call is a cache read on
a hit (cheap), and unconditional sequencing is simpler than branching bot
logic on a status that may be stale by the time the button is tapped.

### AD-6: No eager trigger anywhere; the button tap is the single, sequential trigger point

Rejected alternatives (background priming at question-display time or
post-check time, with or without an in-process dedup registry) are recorded
in Problem & Motivation. The sequential design removes the concurrency
question by construction: there is exactly one call path that can invoke
the judge for a given tap.

### AD-7: Bot keyboard and message-editing changes

- `handle_answer_callback` no longer calls `get_explanation`; it renders
  only the outcome line, with a keyboard of `["Spiega"]` +
  `["Prossima domanda ▶"]` (only the latter when `explanation_status ==
  UNAVAILABLE`).
- A new callback handler (`quiz:explain:{number}:{answer}`) calls
  `QuizFlowService.handle_explanation_request`, then edits the same message
  (`query.edit_message_text`/`edit_message_caption`, following the existing
  pattern at `quiz_handlers.py:146-150`), appending the explanation (or the
  existing `messages.NO_EXPLANATION_LINE` on failure) to the message's
  current text/caption, and replaces the keyboard with the existing
  `_NEXT_KEYBOARD` constant.
- `QuizFlowService.handle_answer` returns `(correct, explanation_status)`
  instead of `(correct, QuizExplanation)`.
- A new `QuizFlowService.handle_explanation_request(session, number,
  telegram_user_id, submitted)` performs the `label` → `explanation`
  sequence, reusing the existing `QuizApiError` → `insufficient_knowledge`
  fallback (`quiz_flow_service.py:56-63`) around both calls.

### AD-8: A bot-side `ExplanationStatus` enum mirrors the API's

`QuizApiClient.check_answer`'s return type changes from `bool` to
`tuple[bool, ExplanationStatus]` (new bot-side enum, distinct from the
existing `ExplanationOutcome` used for explanation *results*), so the
handler can decide whether to render the "Spiega" button.

### AD-9: Testing

- Unit tests for `CurrentLabelingReadService` and the refactored
  `CommaSelectorService`/`ExplanationService`, with `GoldenSetReadRepository`
  and `QuizQuestionRepository` mocked, covering all three "no current
  labeling" shapes (not indexed / has commas / no commas) plus the new
  `LabelingNotReadyError` path.
- A router-level integration test for `POST /label` and the narrowed
  `GET /explanation` against the ephemeral test Postgres stack
  (`docker/docker-compose.test.yml`), per existing convention
  (`.claude/rules/code-conventions.md`, `@pytest.mark.integration`).
- Bot-side tests for `QuizFlowService.handle_explanation_request` and the
  new callback handler with a faked `QuizApiClient`, covering: normal
  explain, `UNAVAILABLE` (no button shown), and a `QuizApiError` from either
  `/label` or `/explanation` (fallback rendering).

### AD-10: `/label` runs under its own explicit deadline, covering retrieval+judge

Rather than relying only on the bot's HTTP client timeout (which would
leave the judge running server-side after the bot gives up on the
connection), `/label`'s implementation wraps the `CommaSelectorService`
call in `asyncio.timeout`, the same pattern `ExplanationService._explain`
uses today (`explanation_service.py:83-95`). The config value is a new
`AppConfig` field (exact name left to implementation, e.g.
`labeling_deadline_s`), replacing the retrieval+judge portion of today's
`explanation_deadline_s`. Exceeding it raises the existing
`ExplanationUnavailableError`, mapped to `503`, unchanged.

### AD-11: `/explanation`'s deadline shrinks to cover only the writer stage

With retrieval+judge moved to `/label`, `/explanation`'s own deadline no
longer needs to budget for the ~11k-token judge call — only
`ExplanationWriterAgent.run` and its citation-grounding retries
(`explanation_service.py:126-159`). This is a new, much shorter `AppConfig`
value (exact name left to implementation), replacing `explanation_deadline_s`
for this endpoint.

### AD-12: One unified failure fallback, no distinction by cause

A `/label` timeout (AD-10), a judge failure, a writer failure, and the new
`LabelingNotReadyError` (AD-4) all reach the bot as some `QuizApiError` and
all render the same existing fallback (`messages.NO_EXPLANATION_LINE`, no
retry affordance) — the same treatment `handle_answer` already gives an
`/explanation` failure today (`quiz_flow_service.py:56-63`). Deliberately
not split into "transient, retry" vs. "permanent, no retry": kept simple
per this project's stated "simple even at some cost" priority (spec 0016),
revisited only if it proves confusing in practice.

### AD-13: Optimistic UI update on tap prevents a double-tap on "Spiega"

The first edit (FR-3) — removing "Spiega" from the keyboard and adding the
loading line — happens before `/label` is even called, so a second tap on
the same message cannot happen: the button is gone from the message the
moment the first tap is handled. This is simpler than any request-level
guard (in-flight tracking, idempotency key) and needs no new bot-side
state.

### AD-14: "Prossima domanda ▶" stays active during the loading wait

Deliberately not disabled alongside "Spiega" (AD-13): the user is free to
move on while an explanation loads for the previous question. The
in-flight sequence's final edit still lands on the now-superseded message
when it completes — a cosmetic no-op from the user's point of view, not a
correctness issue, since nothing about the new question's flow depends on
that edit.

## Note for future work

The user explicitly asked that this be recorded: endpoints — and the
services they call — should each have a single, well-defined
responsibility. This spec is a concrete instance of applying that principle
(splitting "ensure labeled" from "render explanation" instead of one
endpoint doing both). Once implemented, this is worth promoting to a
documented pattern via `second-brain:update` (candidate home:
`docs/second-brain/patterns.md` or `.claude/rules/code-conventions.md`) so
it guides future endpoint/service design, not just this feature.

## Data Model

No schema changes. `/label` and the narrowed `/explanation` both read/write
the existing `quiz_labelings`, `quiz_comma_labels`, and `labeling_runs`
tables through the existing `GoldenSetReadRepository`/`GoldenSetWriteRepository`.

## Constraints

- `AppConfig.explanation_deadline_s` (`explanation_service.py:39-55, 84`)
  is replaced by two new values per AD-10/AD-11: one for `/label`
  (retrieval+judge, similar magnitude to today's ~25s) and one for
  `/explanation` (writer only, much shorter). Exact field names are left to
  implementation.
- Router bodies stay thin controllers — no `try/except` or status-code
  mapping in `api/routers/quiz_questions.py` (existing convention, e.g.
  `quiz_questions.py:75-118`); the new `LabelingNotReadyError` → 409 mapping
  goes in the existing global exception-handler registration.
- pywire field-injection conventions
  (`.claude/rules/pywire-di.md`) apply unchanged to any new
  `@service`/`@repository` class.
- Bot-side changes follow `.claude/rules/pywire-di.md`'s bot scope (field
  injection in `services/`/`clients/`) and existing handler conventions in
  `quiz_handlers.py`.

## Feasibility Evidence

- **FR-3/AD-1** — supported by: `src/guidami_ai_patente_bot/services/quiz_flow_service.py:42-64` — `handle_answer` currently calls `check_answer` and `get_explanation` together in one method (verified 2026-09-18)
- **FR-4/AD-2** — supported by: `src/guidami_ai_patente/services/comma_selector_service.py:22-67` — `CommaSelectorService.execute` already implements "cache hit reads, cache miss computes and writes" (verified 2026-09-18)
- **FR-5/AD-3** — supported by: `src/guidami_ai_patente/services/explanation_service.py:66-99` — `ExplanationService.selector: Autowired[CommaSelectorService]`, called at line 99 with no distinction between a cache hit and a live-computed result (verified 2026-09-18)
- **AD-3** — supported by: `src/guidami_ai_patente/services/comma_selector_service.py:63-67, 121-133` — the hit-branch logic (`find_current_labeling` + `_selection_for`) is already isolated enough to extract (verified 2026-09-18)
- **AD-4** — supported by: `src/guidami_ai_patente/services/explanation_status_service.py:32-51` — the three-way classification (cached / no-commas / not-indexed) this spec's `CurrentLabelingReadService` must mirror already exists here (verified 2026-09-18)
- **AD-4** — supported by: `src/guidami_ai_patente/exceptions/` (directory listing: `explanation_unavailable_error.py`, `question_not_found_error.py`, `quiz_image_not_found_error.py`, `unregistered_user_error.py`, `guidami_api_error.py`) — confirms the existing one-exception-per-file convention `LabelingNotReadyError` follows (verified 2026-09-18)
- **FR-6/AD-8** — supported by: `src/guidami_ai_patente_bot/clients/quiz_api_client.py:58-68` — `check_answer` returns only `bool(response.json()["correct"])`, discarding `explanation_status` (verified 2026-09-18)
- **AD-7** — supported by: `src/guidami_ai_patente_bot/handlers/quiz_handlers.py:107-150` — existing callback-handler and `edit_message_text`/`edit_message_caption` pattern the new "Spiega" handler follows (verified 2026-09-18)
- **AD-1 (rejected: eager-in-check)** — supported by: `docs/second-brain/architecture.md:1241-1242` (via `second-brain:second-brain-reader`, 2026-09-18) — "keeps the hot `POST /check` path — which only reads the epoch — from ever building an LLM graph it never calls" (ADR 0029)

## Open Questions

- [ ] **non-blocking** — exact method shape of `CurrentLabelingReadService` (its name is settled, AD-3) — left to implementation.
- [ ] **non-blocking** — exact `AppConfig` field names for the two new deadlines (AD-10, AD-11) — left to implementation.

## Sign-off

- **Scope approved by user:** yes (2026-09-18, plan grilling round)
- **Feasibility asserted:** by the assistant on 2026-09-18, based on Feasibility Evidence above (source reads, not a dedicated feasibility-compiling skill) — confirmed correct by implementation

## Changelog

- **2026-09-18** — Initial draft, from an interactive `superpowers:brainstorming` session.
- **2026-09-18** — Amended after a `mattpocock-skills:grilling` round (AD-10
  through AD-14, plus FR-3/FR-4/FR-5 and Constraints updates): split
  `explanation_deadline_s` into a `/label`-side deadline (retrieval+judge)
  and a much shorter `/explanation`-side deadline (writer only); confirmed
  `/label` returns `204 No Content`; confirmed one unified failure fallback
  covers `/label` timeouts too, with no retry affordance; added the
  optimistic UI edit (remove "Spiega", show a loading line) on tap to
  prevent a double-tap, with "Prossima domanda ▶" deliberately left active
  during the wait. Non-material amendment — status stays draft.
- **2026-09-18** — Named the new read-only component from AD-3
  `CommaSelectionService` (not `CommaSelectionReader`), per this project's
  `*Service` fallback naming convention for a domain component with
  injected dependencies. Non-material amendment — status stays draft.
- **2026-09-18** — Renamed the AD-3 component again, from
  `CommaSelectionService` to `CurrentLabelingReadService`: the previous name
  described only the output shape (`CommaSelection`), not that the
  component is read-only. The new name mirrors the existing
  `CurrentLabeling` domain model and `GoldenSetReadRepository`'s `Read`
  prefix, making the read-only nature explicit. Non-material amendment —
  status stays draft.
- **2026-09-18** — Implemented (Tasks 1-10 of
  `docs/superpowers/plans/2026-09-18-on-demand-explanation.md`). Status: implemented.
