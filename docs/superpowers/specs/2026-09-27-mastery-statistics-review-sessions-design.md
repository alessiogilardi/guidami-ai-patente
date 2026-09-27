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

# Spec 0024: Mastery statistics & targeted review sessions

| | |
|---|---|
| **Id** | 0024 |
| **Status** | draft |
| **Date** | 2026-09-27 |
| **Discussion log** | — (brainstorming + grilling held in-session, decisions recorded as D-n below) |
| **Supersedes / superseded by** | — |

## Problem & Motivation

Spec 0016 made every submitted answer durable in `quiz_answers`, but the only
read-back is the `/stop` summary of the one session just played (spec 0016
Non-Goals explicitly excluded cross-session statistics). The user therefore
cannot see **where they make the most mistakes**, and every question is still
drawn from a uniform seeded permutation (`GET /quiz-questions/random`), so a
question the user keeps getting wrong is no more likely to come back than one
they have mastered.

This spec adds two things on top of the existing answer history, with no new
table:

1. A **mastery model** — one shared definition of "this question needs review"
   and "this topic is weak" — surfaced to the user as `/statistiche`.
2. **Targeted sessions** — a review mode that insists on the questions the user
   has been getting wrong (`/ripasso`), and a topic-filtered mode (`/argomento`)
   exposing the `topic` filter `/random` already supports.

It is sub-projects **A + B** of a larger roadmap agreed during brainstorming
(see Non-Goals for C–F). A is the foundation the later sub-projects reuse, so
the definition of weakness lives in exactly one place.

## Decisions log (brainstorming + grilling, 2026-09-27)

| Id | Decision | Rejected alternatives |
|---|---|---|
| D-1 | Scope is A (mastery + `/statistiche`) + B (targeted sessions) in one spec | A alone; exam simulation first |
| D-2 | Weakness = **derived Leitner**: a question is *in review* when answered wrongly at least once and, since the last wrong answer, answered correctly fewer than N times in a row. Derived on read from `quiz_answers`, never materialized | error-rate weighting with decay; materialized SRS state table |
| D-3 | Review questions are served by a **server-side `next` endpoint** keyed by `session_id`; the bot keeps no list | snapshot of weak numbers held by the bot; `mode=review` on `/random` |
| D-4 | Modes in scope: review-of-errors + topic-filtered quiz; no automatic weak-topic mode | errors only; auto weak-topic sampling |
| D-5 | `/statistiche` shows totals + coverage, per-topic mastery weakest first, review count; no time trend | adding a 7-day trend |
| D-6 | Dedicated bot commands `/statistiche`, `/ripasso`, `/argomento`; `/quiz` unchanged | mode menu under `/quiz`; buttons under statistics only |
| D-7 | Mastery logic in a pure Python `MasteryCalculator` over a compact per-user history loaded by one query | window functions in SQL |
| D-8 | A question wrongly answered **during** a review session is re-proposed in the same session, after the not-yet-seen ones | once per session; interleaved after M questions |
| D-9 | At most 2 re-proposals of the same question per session (configurable) | unbounded; end session instead of immediate re-ask |
| D-10 | Review priority: current correct streak ascending → `wrong_count` descending → seeded hash | `wrong_count` only; most recent error first |
| D-11 | Topics with fewer than K seen questions form a separate "Da esplorare" group listed after the ranked ones | on top; merged as 0% |
| D-12 | Statistics path is `GET /quiz-answers/statistics` (sibling of `/quiz-answers/summary`) | `GET /me/statistics` |
| D-13 | No topic filter on review in this spec | backend-only param; end-to-end filter |
| D-14 | A `TOPIC` session whose permutation is exhausted ends with a completion message + the `/stop` summary; backend unchanged | restart with a new seed; change `/random` to 204 |
| D-15 | *Mastered* = seen and not in review, so `seen = mastered + in_review` always holds | "last answer correct" |

## Functional Requirements

### FR-1: Per-question mastery state is derived from the user's answer history

For one user, each question they have answered at least once has a state
computed from that user's `quiz_answers` rows for it, taken in insertion order
(`quiz_answers.id`), with correctness derived by comparing `user_answer`
against `quiz_questions.correct_answer` (never cached, spec 0016 AD-3):

- `wrong_count` — number of wrong answers ever.
- `streak` — number of consecutive correct answers after the most recent wrong
  one (for a never-wrong question, the number of correct answers; irrelevant to
  `in_review`).
- `in_review` — `wrong_count > 0 and streak < review_exit_streak`.
- `mastered` — `not in_review`.

Answers from every mode (random, topic, review) count identically.

**Acceptance criteria** (with `review_exit_streak = 2`):
- Given answers ✓✓ for a question, then `in_review` is false, `mastered` is true.
- Given ✗, then `in_review` is true, `streak = 0`, `wrong_count = 1`.
- Given ✗✓, then `in_review` is true, `streak = 1`.
- Given ✗✓✓, then `in_review` is false, `wrong_count = 1`.
- Given ✗✓✗, then `in_review` is true, `streak = 0`, `wrong_count = 2`.
- Given answers from two different users on the same question, then each
  user's state is computed from their own rows only.

### FR-2: Per-topic mastery ranks topics from weakest, with an insufficient-data group

For each topic in the quiz bank, the topic's mastery is `seen` (distinct
questions of that topic the user answered at least once), `mastered` (those of
them with `mastered = true`, FR-1) and `total` (questions in the bank for that
topic). Topics with `seen >= topic_min_seen` are *ranked*, ordered by
`mastered / seen` ascending (ties broken by topic name). Topics with
`seen < topic_min_seen` (including `seen = 0`) are *insufficient data*, listed
after all ranked topics, ordered by `seen / total` ascending (ties by name).

**Acceptance criteria** (with `topic_min_seen = 5`):
- Given topic T has 10 seen questions, 4 mastered, and topic U has 10 seen, 8
  mastered, then T is listed before U, both as ranked.
- Given topic V has 3 seen questions, all mastered, then V is in the
  insufficient-data group, after every ranked topic, and is not presented as
  100%.
- Given a topic the user has never answered, it appears in the
  insufficient-data group with `seen = 0`.
- Given a question answered wrongly then correctly ten times, its topic's
  `mastered` counts it once (distinct questions, not attempts).
- For every topic, `seen = mastered + in_review_count`.

### FR-3: `GET /quiz-answers/statistics` returns the user's overall statistics

Gated by `require_registered_user` like every quiz route (spec 0016 FR-3).
Returns: `answered` (total answer rows), `seen` (distinct questions answered),
`bank_total` (questions in the bank), `mastered`, `in_review` (counts over all
seen questions, FR-1), and `topics` (FR-2 ordering, each with `topic`, `seen`,
`mastered`, `total`, `insufficient_data: bool`).

**Acceptance criteria:**
- Given a registered user with no answers, then `200` with every count `0`
  except `bank_total`, and every topic present in the insufficient-data group.
- Given a registered user with answers, then `seen = mastered + in_review`.
- Given an unregistered caller, then `403` (existing handler).
- Given two users, then each sees only their own statistics.

### FR-4: `GET /quiz-questions/review/next?session_id=` serves the next review question

Gated by `require_registered_user`. Returns `200` with the question in the same
shape as `GET /quiz-questions/random` (never `correct_answer`), or `204` when
the review session is complete. Selection, given the user's FR-1 states and
their answers tagged with this `session_id`:

1. **Unseen-in-session pass** — among questions with `in_review = true` that
   have no answer in this session, pick by `streak` ascending, then
   `wrong_count` descending, then `md5(session_id || number)` ascending.
2. **Re-ask pass** (only when pass 1 is empty) — among questions answered in
   this session whose most recent answer in this session is wrong and whose
   number of answers in this session is `<= review_max_repeats_per_session`,
   pick the one whose last in-session answer is oldest.
3. Otherwise `204`.

**Acceptance criteria** (`review_exit_streak = 2`, `review_max_repeats_per_session = 2`):
- Given in-review questions A (streak 0, 1 wrong) and B (streak 1, 3 wrong),
  then A is served before B.
- Given C and D both streak 0, C with 3 wrong and D with 1, then C before D.
- Given two questions equal on streak and `wrong_count`, then the order is
  identical across repeated calls with the same `session_id`.
- Given A was answered correctly in this session, then A is not served again
  in this session.
- Given A was answered wrongly in this session and other unseen in-review
  questions remain, then those are served before A comes back.
- Given A has been answered wrongly 3 times in this session (1 + 2
  re-proposals), then A is not served again in this session and remains
  `in_review`.
- Given a user with no in-review questions, then `204`.
- Given an unregistered caller, then `403`.

### FR-5: Answers given in review/topic sessions are recorded unchanged

`POST /quiz-questions/{number}/check` is not modified: the bot sends the
session's seed as `session_id` in every mode, so review answers land in
`quiz_answers` and update FR-1 state for the next `next` call.

**Acceptance criteria:**
- Given `next` served A in session S and A is then answered via `/check`
  with `session_id = S`, then the following `next` call for S reflects that
  answer (A is excluded if correct, queued for re-ask if wrong).

### FR-6: `/statistiche` shows the user's statistics

The bot calls `GET /quiz-answers/statistics` and renders: one totals line
(seen / bank total, mastered %), ranked topics with their mastery %, the
"Da esplorare" group with seen/total, and a closing line with the review count
and a hint to `/ripasso` (omitted when `in_review = 0`). Topic names are shown
with the short label of FR-9.

**Acceptance criteria:**
- Given the backend returns ranked and insufficient-data topics, then ranked
  ones appear first, then a "Da esplorare" header with the others.
- Given `in_review = 0`, then no `/ripasso` hint is shown.
- Given the message exceeds Telegram's length limit, then it is split with the
  existing chunked `_send_text` helper.

### FR-7: `/ripasso` starts a review session

Starts a fresh `REVIEW` session (new seed), replacing any in-progress session,
and proposes its first question via FR-4. If the first `next` returns `204`,
replies "Nessun errore da ripassare" and leaves no session. After each answer,
"Avanti" calls `next` again; a `204` mid-session shows a completion message
followed by the same summary `/stop` shows, and clears the session.

**Acceptance criteria:**
- Given a pending random-mode question, when `/ripasso` is sent, then the
  session is replaced by a `REVIEW` session and the old question's buttons
  become stale (existing stale guard).
- Given no in-review questions, then the "nessun errore" reply is sent and
  `context.user_data` holds no session.
- Given `next` returns `204` after the user's last answer, then completion
  message + session summary are shown and the session is cleared.

### FR-8: `/argomento` starts a topic-filtered session

Shows an inline keyboard with every topic, in FR-2 order (from
`GET /quiz-answers/statistics`), each button labelled with the FR-9 short
label plus the mastery % (ranked) or seen/total (insufficient data). Tapping
one starts a fresh `TOPIC` session (new seed) replacing any in-progress
session, proposing questions via `/random?seed&index&topic=`. When `/random`
returns `404` in `TOPIC` mode, the session ends with an "argomento completato"
message followed by the session summary, and is cleared (D-14).

**Acceptance criteria:**
- Given the keyboard was shown, when a topic button is tapped, then the next
  question comes from that topic only.
- Given a topic keyboard older than the most recently shown one, when one of
  its buttons is tapped, then it is treated as a stale button (existing
  stale-button message) and no session is started.
- Given the user answered every question of the topic, then the completion
  message + summary are shown and the session is cleared.
- Given `/random` returns `404` in `RANDOM` mode, then behavior is unchanged
  from today (generic error path).

### FR-9: Topic labels and callback data fit Telegram's limits

Topic names in the bank reach 345 bytes; Telegram caps `callback_data` at 64
bytes. Button callback data is `topic:<token>:<i>` (AD-8), where `i` indexes
the topic list stored in `context.user_data` alongside the keyboard; the full
topic name never travels in callback data. The visible label is the topic name up to its first
`;`, truncated to `topic_label_max_chars` (bot config, default 40) with an
ellipsis when longer.

**Acceptance criteria:**
- Given a 345-byte topic name, then its `callback_data` is at most 64 bytes.
- Given `"Segnali di pericolo; ..."`, then the label is `"Segnali di pericolo"`.
- Given a first segment longer than the limit, then it is truncated with `…`.

## Non-Goals

- **Roadmap sub-projects, each its own future spec**: C — exam simulation
  (30 questions, 20 minutes, max 3 errors, per-chapter distribution); D —
  readiness index (estimated pass probability from per-topic mastery weighted
  by the exam distribution); E — "trap pairs" (near-identical questions with
  opposite answers, found via existing question embeddings); F — scheduled
  review reminders (true spaced repetition with due dates, the point at which a
  materialized state table would be reconsidered, D-2).
- A topic filter on review (D-13).
- An accuracy trend over time in `/statistiche` (D-5).
- Persisting `QuizSession` across bot restarts (still open in
  `discussions/bot-persistent-session.md`). Review mode tolerates a restart by
  construction: `/ripasso` starts a new `session_id` and the backend derives
  everything else.
- Fixing `ingest reset quiz` (known broken for the FK reason, already deferred
  in `database.md`). This spec relies on `quiz_questions.id` being stable
  across re-ingestion, which the upsert write path preserves.
- Any change to `/quiz`'s resume-if-pending behavior (spec 0016 FR-8).

## Architectural Decisions

### AD-1: No new table; one composite index

Mastery is derived on read (D-2). The only schema change is
`CREATE INDEX IF NOT EXISTS idx_quiz_answers_user_id_id ON quiz_answers (user_id, id)`,
so one user's history is read in insertion order from the index. It goes in
`db/init.sql` **and** an idempotent `db/migrations/0024_quiz_answers_user_history_index.sql`
(CLAUDE.md "Applying a schema change", path 2). The existing single-column
`idx_quiz_answers_user_id` becomes redundant and is dropped in the same
migration (`DROP INDEX IF EXISTS`) and removed from `init.sql`.

### AD-2: One history query, logic in Python (D-7)

`QuizAnswerRepository.user_history(telegram_user_id) -> list[AnsweredQuestion]`
returns `(number, topic, session_id, is_correct)` rows ordered by `qa.id`, with
`is_correct` computed in SQL as `qa.user_answer = q.correct_answer` (spec 0016
AD-3 posture: correctness is never stored). `AnsweredQuestion` is a new frozen
model in `guidami_ai_patente/models/`. All mastery rules live in
`MasteryCalculator`; the repository contains no business rule.

Trade-off accepted: every statistics/next call loads the user's full history.
At personal scale this is a few thousand rows at most; the revisit trigger is
roughly 50k rows per user.

### AD-3: `MasteryCalculator` — pure, stateless, a named dependency

`services/mastery_calculator.py`, decorated `@service` with only
`Autowired[AppConfig]` (for `review_exit_streak`, `topic_min_seen`). Methods:

- `question_states(history) -> dict[str, QuestionMastery]` (FR-1)
- `topic_mastery(states, topic_totals) -> list[TopicMastery]` (FR-2)

`QuestionMastery` and `TopicMastery` are frozen models in `models/`. Not a
`UseCase`: two distinct operations (use-case-invocation.md "more than one
distinct public operation").

### AD-4: `UserStatisticsService` and `ReviewQuestionService` are `UseCase`s

- `UserStatisticsService: UseCase[int, UserStatistics]` — input
  `telegram_user_id`; loads history + `QuizQuestionRepository.list_topics()`
  (already returns per-topic totals), delegates to `MasteryCalculator`.
- `ReviewQuestionService: UseCase[ReviewRequest, QuizQuestionSummary | None]` —
  `ReviewRequest(telegram_user_id, session_id)`; applies FR-4's two passes over
  `question_states` plus the in-session slice of the same history, then fetches
  the chosen question with `QuizQuestionRepository.find_by_number` (same
  projection as `/random`). The seeded tie-break is `hashlib.md5` over
  `session_id + number` in Python, matching the spirit of the SQL permutation.

Both are invoked via `__call__` and added to the use-case-invocation.md scope
list.

### AD-5: Endpoints

- `GET /quiz-answers/statistics` in the existing `api/routers/quiz_answers.py`,
  response schema `UserStatisticsResponse` in `api/schemas/`.
- `GET /quiz-questions/review/next?session_id=` in `api/routers/quiz_questions.py`,
  declared before `/{number}` routes; `204` via `Response(status_code=204)` when
  the use case returns `None`.

Both depend on `require_registered_user` (spec 0016 AD-4) and cross into the
sync repository layer with `asyncio.to_thread` like the existing routes.

### AD-6: Configuration

`AppConfig` gains `review_exit_streak: int = Field(default=2, ge=1)`,
`review_max_repeats_per_session: int = Field(default=2, ge=0)`,
`topic_min_seen: int = Field(default=5, ge=1)`. `BotConfig` gains
`topic_label_max_chars: int = Field(default=40, ge=10)`.

### AD-7: Bot session carries its mode

`QuizSession` gains `mode: SessionMode` (default `RANDOM`) and
`topic: str | None = None`. `SessionMode` is a `StrEnum` in
`guidami_ai_patente_bot/enums/` with `auto()` values (bot-internal, never on
the wire). `seed` remains the `session_id` in every mode, so `/check` and the
`/stop` summary need no change. `index` is unused in `REVIEW` mode.

`QuizFlowService.propose_question` dispatches on `mode`:
`RANDOM` → `/random?seed&index`; `TOPIC` → `/random?seed&index&topic`;
`REVIEW` → `/quiz-questions/review/next?session_id=seed`. Pool exhaustion
(`204` in `REVIEW`, `404` in `TOPIC`) is surfaced as a new
`SessionCompletedError` raised by the service, which handlers render as
completion message + summary (FR-7, FR-8). `QuizApiClient` returns `None` for
a `204`/`404` on these two calls rather than raising, so the service — not the
client — decides that "no question" means "session complete" and only in the
modes where it does.

### AD-8: Topic keyboard state

When `/argomento` renders its keyboard it stores the ordered list of full topic
names in `context.user_data["topic_choices"]` plus a keyboard token; callback
data is `topic:<token>:<i>`. A tap whose token differs from the stored one is
stale (FR-8). `<token>` is a short random hex (8 chars), keeping the payload
well under 64 bytes.

## Data Model

No new table. New index (AD-1). New models:

| Model | Package | Fields |
|---|---|---|
| `AnsweredQuestion` | `guidami_ai_patente/models/` | `number`, `topic`, `session_id`, `is_correct` |
| `QuestionMastery` | `guidami_ai_patente/models/` | `number`, `topic`, `wrong_count`, `streak`, `in_review` (+ `mastered` property) |
| `TopicMastery` | `guidami_ai_patente/models/` | `topic`, `seen`, `mastered`, `total`, `insufficient_data` |
| `UserStatistics` | `guidami_ai_patente/models/` | `answered`, `seen`, `bank_total`, `mastered`, `in_review`, `topics` |
| `ReviewRequest` | `guidami_ai_patente/models/` | `telegram_user_id`, `session_id` |
| `UserStatistics`, `TopicMastery` (bot mirrors) | `guidami_ai_patente_bot/models/` | same wire shape, declared independently (spec 0015 AD-1) |

## Constraints

- The bot never touches Postgres; everything goes through the HTTP API.
- pywire field injection for every new `@service`/`@repository` (pywire-di.md).
- Correctness is always derived, never stored (spec 0016 AD-3).
- Integration tests use only the ephemeral test stack, never the dev database.
- The dev database is migrated with the additive script (AD-1), never wiped;
  verify `SELECT count(*) FROM quiz_answers` is unchanged before/after.

## Feasibility Evidence

- **AD-2 (correctness derivable)** — `db/init.sql:218-225`: `quiz_answers`
  holds `user_id`, `quiz_id`, `session_id`, `user_answer`; `correct_answer`
  lives on `quiz_questions` (verified 2026-09-27).
- **AD-4 (topic totals available)** —
  `src/guidami_ai_patente/repositories/quiz_question_repository.py:87-95`:
  `list_topics()` returns every topic with its `question_count` (verified
  2026-09-27).
- **AD-4 (same projection as `/random`)** — same file, lines 63-73:
  `find_by_number` shares `find_by_permutation`'s projection (verified
  2026-09-27).
- **FR-8/D-14 (`/random` exhausts)** — same file, lines 50-53 and
  `services/quiz_proposal_service.py:30-37`: `None` past the end, rendered as
  `QuestionNotFoundError` → 404 (verified 2026-09-27).
- **FR-9 (topic length)** — `data/parsed/quiz-patente-ab/quiz-patente-ab.json`:
  25 topics, longest 345 bytes UTF-8 (verified 2026-09-27).
- **AD-7 (single HTTP chokepoint)** —
  `src/guidami_ai_patente_bot/clients/quiz_api_client.py:143-171`: `_request`
  raises `QuizApiError` on any non-2xx other than 403, so the 404-as-`None`
  handling must be explicit in the two affected client methods (verified
  2026-09-27).
- **AD-7 (session_id = seed)** —
  `src/guidami_ai_patente_bot/services/quiz_flow_service.py` `handle_answer`
  sends `session.seed` as `session_id` (verified 2026-09-27).

## Definition of Done

- `db/init.sql` and `db/migrations/0024_quiz_answers_user_history_index.sql`
  updated (AD-1); migration applied to the dev stack with `quiz_answers`
  row count verified unchanged.
- `MasteryCalculator` unit-tested against every FR-1/FR-2 criterion.
- `ReviewQuestionService` unit-tested with substitute repositories against
  every FR-4 criterion (ordering, determinism, re-ask pass, repeat cap, `None`).
- `QuizAnswerRepository.user_history` integration-tested (ordering by id,
  per-user isolation, `is_correct` derivation).
- Both endpoints integration-tested: `200`/`204`, `403` for unregistered, and
  the `next → check → next` loop of FR-5.
- Bot: `QuizFlowService` unit-tested per mode (correct endpoint per mode,
  `SessionCompletedError` on `204`/`404` only in `REVIEW`/`TOPIC`); handler
  tests for `/statistiche` rendering, `/ripasso` empty case, `/argomento`
  stale keyboard; FR-9 label/callback tests.
- Manual Telegram session: answer some questions wrong via `/quiz`, see them
  in `/statistiche`, clear them via `/ripasso` (including one in-session
  re-ask), train a small topic to completion via `/argomento`.
- `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` pass.
- CLAUDE.md endpoint table, `.claude/rules/use-case-invocation.md` scope list,
  and `docs/second-brain/` (`architecture.md`, `database.md` index,
  `glossary.md` for *in review*/*mastered*) updated via `second-brain:update`
  before push.

## Open Questions

- none blocking. Default values of N (2), repeat cap (2) and K (5) are
  configurable and may be tuned after real use.

## Sign-off

- **Scope approved by user:** pending review of this document.
- **Feasibility asserted:** by brainstorming on 2026-09-27, based on
  Feasibility Evidence above.
