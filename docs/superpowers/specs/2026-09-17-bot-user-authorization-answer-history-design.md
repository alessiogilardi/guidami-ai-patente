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

# Spec 0016: Telegram bot user authorization & quiz-answer history

| | |
|---|---|
| **Id** | 0016 |
| **Status** | draft |
| **Date** | 2026-09-17 |
| **Discussion log** | docs/superpowers/specs/discussions/bot-persistent-session.md |
| **Supersedes / superseded by** | — |

## Problem & Motivation

The Telegram bot (spec 0015) keeps all state in `context.user_data` for the
process lifetime only — nothing survives a restart, and anyone who finds the
bot can use it immediately, with no way to restrict access to approved
users. This spec adds the first slice of DB-backed persistence: a whitelist
of authorized Telegram users, and a history of the answers they submit. It
deliberately does **not** persist the in-progress quiz session itself
(`QuizSession` — seed/index/current question) — that stays in-memory, as a
separate, later increment.

Priority stated by the user throughout brainstorming: keep the design
simple, even at some performance cost — this is a personal-scale project,
not a high-throughput service. The bot must never talk to Postgres directly;
only the FastAPI backend (`guidami_ai_patente`) accesses the database, and
the bot reaches it exclusively over the HTTP API it already calls today.

## Functional Requirements

### FR-1: A `users` row is provisioned automatically on first contact

Given a `telegram_user_id` with no existing `users` row, the first request
carrying that id (to any endpoint that resolves identity) creates one, with
`registered = false`.

**Acceptance criteria:**
- Given no `users` row exists for `telegram_user_id = 42`, when a request
  arrives with header `X-Telegram-User-Id: 42` to any identity-resolving
  endpoint, then a `users` row is created for `telegram_user_id = 42` with
  `registered = false`.
- Given a `users` row already exists for `telegram_user_id = 42` (regardless
  of its `registered` value), when another request arrives with the same
  header, then no second row is created and the existing row's `registered`
  value is left untouched (`INSERT ... ON CONFLICT (telegram_user_id) DO
  NOTHING`).

### FR-2: `GET /me` reports registration status and never rejects

Given any `telegram_user_id`, `GET /me` resolves/provisions the user (FR-1)
and reports whether they are registered — it never responds with 403, since
"not yet approved" is itself a valid, successful answer for this endpoint.

**Acceptance criteria:**
- Given `telegram_user_id = 42` has no prior `users` row, when
  `GET /me` is called with `X-Telegram-User-Id: 42`, then the response is
  `200 OK` reporting `registered: false`, and a `users` row now exists for
  `42` with `registered = false` (FR-1).
- Given a `users` row exists for `telegram_user_id = 42` with
  `registered = true`, when `GET /me` is called with that header, then the
  response is `200 OK` reporting `registered: true`.

### FR-3: Every quiz-related endpoint requires an already-registered caller

Given any endpoint other than `GET /health` and `GET /me`, the request is
rejected unless the caller's `telegram_user_id` resolves to a `users` row
with `registered = true`.

**Acceptance criteria:**
- Given `telegram_user_id = 42` has no `users` row (or one with
  `registered = false`), when a request with `X-Telegram-User-Id: 42` hits
  any of `GET /quiz-questions/topics`, `GET /quiz-questions/random`,
  `GET /quiz-questions/{number}`, `POST /quiz-questions/{number}/check`,
  `GET /quiz-questions/{number}/explanation`, `GET /quiz-images/{filename}`,
  or the new session-summary endpoint (AD-16), then the response is
  `403 Forbidden` and no business logic for that endpoint executes.
- Given the same call, a `users` row for `42` exists afterwards with
  `registered = false` (the rejection still provisions the row, per FR-1,
  so the request is visible for manual approval).
- Given `telegram_user_id = 42` has a `users` row with `registered = true`,
  the same calls succeed exactly as they do today (unchanged response
  shape/behavior beyond this gate).

### FR-4: `GET /health` stays fully public

**Acceptance criteria:**
- `GET /health` succeeds with no `X-Telegram-User-Id` header at all, and its
  response is unchanged by this spec.

### FR-5: Checking an answer persists it to `quiz_answers` in the same request

Given a registered caller submits an answer via
`POST /quiz-questions/{number}/check`, the backend grades it (unchanged
grading behavior) and, in the same request, inserts one `quiz_answers` row
recording the submission, tagged with the session it was answered in.

**Acceptance criteria:**
- Given a registered `users` row for `telegram_user_id = 42` and a
  `quiz_questions` row for `number = "0001"`, when
  `POST /quiz-questions/0001/check` is called with `X-Telegram-User-Id: 42`
  and a body carrying `answer: true` and `session_id: "<seed>"`, then the
  response reports the same grading verdict as today **and** a
  `quiz_answers` row is inserted with `user_id` resolved to the `users.id`
  for `telegram_user_id = 42`, `quiz_id` resolved to the `quiz_questions.id`
  for `number = "0001"`, `user_answer = true`, `session_id = "<seed>"`.
- `session_id` is the bot's existing per-`QuizSession` `uuid4().hex` seed
  (spec 0015, AD-2) — an opaque tag copied onto the row, not a new
  session concept and not a FK to any new table (D-12 in the discussion
  log). No session state beyond this tag is persisted anywhere.
- Given the same question is checked twice by the same user (in the same or
  different sessions), two `quiz_answers` rows exist afterwards — no
  deduplication, no upsert.
- Given the `quiz_answers` insert fails for any reason, the whole request
  fails (no response is returned as if grading alone had succeeded) —
  grading and persistence are not independently fallible from the caller's
  point of view.

### FR-6: The bot attaches the caller's Telegram user id to every backend call

**Acceptance criteria:**
- Every `QuizApiClient` call to the backend (propose, check, explain,
  download image) carries an `X-Telegram-User-Id` header set to
  `update.effective_user.id` of the update that triggered it.

### FR-7: `/start` becomes its own handler — registration status only, no question proposed

`/start` and `/quiz` are split into two distinct commands (D-13), reversing
spec 0015's `CommandHandler(["start", "quiz"], start_or_quiz)`. `/start`
calls `GET /me` and shows a status message; it never proposes a question.

**Acceptance criteria:**
- Given a user sends `/start`, the bot calls `GET /me` and, given
  `registered: false`, replies with a "richiesta in attesa di approvazione"
  message; given `registered: true`, replies with a "benvenuto" message.
- Given either outcome, `/start` never calls `GET /quiz-questions/random`.

### FR-8: `/quiz` is its own handler, with unchanged resume/fresh session logic

`/quiz` no longer aliases `/start` (FR-7), but its own behavior is otherwise
unchanged from spec 0015 FR-1: it does not call `GET /me` first, and it
still reuses the existing seed (advancing `index`) when a session with a
pending, unanswered question already exists in `context.user_data`,
generating a new seed only when no session exists.

**Acceptance criteria:**
- Given a chat with no prior session, when the user sends `/quiz`, a new
  seed is generated and the first question of that permutation is proposed
  (unchanged from spec 0015 FR-1).
- Given a chat with an existing session and a pending, unanswered question,
  when the user sends `/quiz` again, the existing seed is reused and
  `index` advances by one (unchanged from spec 0015 FR-1) — `/quiz` does
  **not** always start a brand-new session on every call (D-14 in the
  discussion log; an earlier draft of this spec assumed otherwise and was
  corrected).
- Given the caller is not registered, `/quiz` gets the same `403` any other
  protected endpoint would (FR-3), surfaced via the generic message (FR-10),
  not `/start`'s differentiated wording.

### FR-9: `/stop` ends the session and shows a proposed/correct summary

Given an active session exists in `context.user_data`, `/stop` fetches how
many questions were answered and how many were correct within that
session, shows the summary, then clears the session.

**Acceptance criteria:**
- Given an active session (seed `S`) with 5 answered questions in
  `quiz_answers` for `session_id = S`, 3 of them correct, when the user
  sends `/stop`, the bot calls the new summary endpoint (AD-16) with
  `session_id = S` and shows "5 domande, 3 corrette" (exact wording is a
  bot-copy detail, not fixed by this spec).
- "Answered" means only rows actually present in `quiz_answers` for that
  session — a question shown but not yet answered at the moment `/stop` is
  pressed is not counted (D-15).
- After showing the summary, the session is cleared from
  `context.user_data`, so the next `/quiz` starts a brand-new session (the
  "no session exists" branch of FR-8).
- Given the summary endpoint call fails (network error, backend down), the
  session is **not** cleared — the user can retry `/stop`, or keep
  answering, without losing access to the not-yet-shown summary (D-16).
- Given no active session exists in `context.user_data` when `/stop` is
  sent, the bot shows a short "nessuna sessione in corso" message and makes
  no backend call.
- Given the caller is not registered (edge case: `registered` was revoked
  mid-session), `/stop` gets the same `403`/generic-message treatment as
  any other protected endpoint (FR-3/FR-10).

### FR-10: Any 403 from the backend shows one friendly message, not a raw error

Given any call to the backend returns `403`, the bot handles it like any
other API failure path (spec 0015 FR-5's single error boundary), but with
wording specific to this case.

**Acceptance criteria:**
- Given a call other than `GET /me` returns `403` (e.g. a `registered=false`
  user skips `/start` and taps a stale inline button), the bot shows
  "Non sei ancora abilitato a usare questo bot." instead of the generic
  failure message, and does not crash.

## Non-Goals

- Persisting the in-progress quiz session (`QuizSession`: seed/index/current
  question) — stays in `context.user_data`, unchanged from spec 0015. A
  later, separate increment.
- Any bot-driven registration/approval flow (a `/richiedi_accesso` command,
  an admin approval command, an owner notification on new signups). Flipping
  `registered` to `true` is a manual, out-of-band action by the project
  owner (e.g. a direct `UPDATE`) — no tooling for it is built here.
- Any bot↔backend shared secret or API key. The design relies on the
  backend being reachable only by the bot today (private network/localhost);
  see AD-12 for the explicit trade-off and its revisit trigger.
- Group chat support. The bot is confirmed private-1:1-only; `chat_id` and
  `telegram_user_id` are treated as interchangeable identifiers for this
  design (see the Discussion log's G-1).
- Exact request/response DTO field names/JSON shapes beyond what FR-1
  through FR-10 state (e.g. `GET /me`'s exact response schema, the extended
  `QuizCheckResponse`'s shape, the new summary endpoint's exact path/JSON
  shape) — left for the implementation plan.
- Any UI/reporting surface for the answer history beyond the one `/stop`
  summary (FR-9) — e.g. cross-session statistics, a history browser, per-
  topic breakdowns. `/stop` reads back only the one session just played.
- `/quiz` ever starting a session forcibly fresh, discarding a pending
  question — considered and explicitly rejected (D-14); `/quiz` keeps spec
  0015 FR-1's resume-if-pending behavior unchanged.

## Architectural Decisions

### AD-1: Two new tables, `users` and `quiz_answers`, English-named
- **Rationale:** every existing table (`articles`, `quiz_questions`,
  `quiz_labelings`, ...) is named in English.
- **Rejected alternatives:** Italian naming (`utenti`, `risposte`), floated
  early in brainstorming — rejected for schema-wide consistency.

### AD-2: `users` schema
```sql
CREATE TABLE users (
    id                BIGSERIAL PRIMARY KEY,
    telegram_user_id  BIGINT NOT NULL UNIQUE,
    registered        BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
- **Rationale:** `id` surrogate for consistency with the project's
  FK-points-at-surrogates convention; `telegram_user_id` is the natural key,
  `UNIQUE NOT NULL`, named distinctly from `quiz_answers.user_id` (an FK to
  `users.id`, not to the Telegram id) to avoid confusion. `registered` is the
  sole authorization flag, flipped manually by the owner. `created_at` for
  bookkeeping, matching every other table.
- **Rejected alternatives:** a `bot_started` boolean — caught as redundant
  during grilling (G-2): with FR-1's upsert-on-first-contact, a row only
  ever exists because contact already happened, so the column would be
  `true` for every existing row; the user confirmed pre-authorization before
  contact never happens. `username`/`first_name` columns — rejected;
  Telegram is already the source of truth and keeps it current, caching it
  here would go stale for no benefit (nothing in scope reads it back).

### AD-3: `quiz_answers` schema
```sql
CREATE TABLE quiz_answers (
    id               BIGSERIAL PRIMARY KEY,
    user_id          BIGINT NOT NULL REFERENCES users(id),
    quiz_id          BIGINT NOT NULL REFERENCES quiz_questions(id),
    session_id       TEXT NOT NULL,
    user_answer      BOOLEAN NOT NULL,
    answer_datetime  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_quiz_answers_user_id ON quiz_answers (user_id);
CREATE INDEX idx_quiz_answers_quiz_id ON quiz_answers (quiz_id);
CREATE INDEX idx_quiz_answers_session_id ON quiz_answers (session_id);
```
- **Rationale:** both FKs point at surrogate ids (`users.id`,
  `quiz_questions.id`), matching the project's existing FK convention (e.g.
  `article_commas.article_id -> articles.id`), even though
  `quiz_questions.number` is the natural key the API/bot otherwise use.
  `user_answer` stores only the raw submitted boolean; correctness is always
  derived via a `JOIN` against `quiz_questions.correct_answer`, never cached,
  so it can't drift out of sync. `answer_datetime` is server-populated
  (`DEFAULT now()`), not client-supplied. No uniqueness constraint on
  `(user_id, quiz_id)` — repeated attempts at the same question are all
  kept. Indexes on all three of `user_id`/`quiz_id`/`session_id` for the
  expected per-user, per-question, and per-session (FR-9) query patterns.
  `session_id` is `TEXT` (not a native `UUID` type) to match the bot's
  existing `uuid4().hex` seed representation as a plain string, with no
  cast layer between the value the bot already holds and what gets stored
  (D-12).
- **`session_id` is not a foreign key.** It is an opaque tag copied from the
  bot's existing per-`QuizSession` seed (spec 0015, AD-2) — deliberately not
  a FK to a new `quiz_sessions` table, since nothing in scope needs
  session-level metadata beyond grouping answers by it (D-12).
- **Rejected alternatives:** a derived `is_correct` column alongside
  `user_answer` — rejected as redundant/driftable; FK to
  `quiz_questions.number` instead of `.id` — rejected for FK-convention
  consistency; a dedicated `quiz_sessions` table with `session_id` as a real
  FK — rejected as unneeded structure (D-12).

### AD-4: Authorization is a FastAPI mechanism applied per-endpoint, not a global ASGI middleware, split into two layers
A base identity-resolution step (provisions the `users` row per FR-1, never
rejects) and `require_registered_user` (built on the base step, additionally
raises `403` when `registered` is `false`) — `GET /me` uses only the base
step, every other non-`/health` endpoint uses `require_registered_user`.
- **Rationale:** the user asked for a per-endpoint OK mechanism, not a
  blanket interceptor. A global Starlette middleware would still need its
  own path-matching to exclude `/health`, so it buys nothing over an
  explicit per-route mechanism, and is less idiomatic for FastAPI here.
  Splitting into two layers is what makes `GET /me`'s "always 200, sometimes
  `registered: false`" contract (FR-2) possible without duplicating the
  provisioning logic.
- **Rejected alternatives:** a single non-splittable dependency (would force
  `GET /me` to either skip provisioning or inherit the 403); a global ASGI
  middleware (see above).
- **Left to the implementation plan (AD-15):** the concrete mechanism —
  whether this is idiomatic FastAPI `Depends()`, and how it composes with
  pywire's `Autowired[T]` route-parameter resolution (see AD-15) — is not
  fixed by this spec.

### AD-5: Identity transport is a single header, `X-Telegram-User-Id`; no profile data travels or is persisted
- **Rationale:** since `users` stores only `telegram_user_id` (AD-2), the
  bot only needs to send that one value. No provisioning endpoint beyond
  `GET /me`, no username/first-name headers.
- **Clarification:** where a *specific* endpoint's own business logic
  genuinely needs a display name (e.g. to personalize a message), it is
  passed as an ordinary field on that endpoint's own request DTO, sourced
  fresh from the Telegram update each time — never as a generic header, and
  never persisted. No such endpoint exists in this spec's scope; this is a
  standing rule for future endpoints that might need one.
- **Rejected alternatives:** sending username/first-name headers on every
  request; a separate one-time provisioning endpoint carrying profile data —
  both moot once `users` dropped profile columns (AD-2).

### AD-6: Provisioning is an idempotent upsert, `ON CONFLICT (telegram_user_id) DO NOTHING`
- **Rationale:** a `registered = true` row must never be silently reset to
  `false` by a later "first contact" from the same id racing a concurrent
  request; `ON CONFLICT DO NOTHING` is atomic at the database level and
  requires no application-level locking.
- **Rejected alternatives:** check-then-insert at the application layer —
  a race window between the check and the insert; requiring the owner to
  pre-create the row — rejected, it removes the owner's visibility into who
  has already tried the bot (see FR-1's second acceptance criterion).

### AD-7: `quiz_answers` insert is a side effect of the same `POST /check` request, not a second call
- **Rationale:** avoids a second round trip and the inconsistent state a
  failed second call would leave (graded but not recorded). See FR-5.
- **Rejected alternatives:** a separate `POST /quiz-answers` called by the
  bot after `/check` returns.

### AD-8: Every endpoint except `GET /health` (and `GET /me`'s own lighter gate, AD-4) requires `require_registered_user`
- **Rationale:** the simplest uniform rule; also closes the gap where an
  unregistered user could otherwise browse quiz content read-only.
- **Rejected alternatives:** gating only endpoints that read/write
  user-specific data (e.g. only `/check`) — rejected in favor of the
  simpler blanket rule.

### AD-9: New repository lives in `guidami_ai_patente/repositories/`, not the ingestor
- **Rationale:** `users`/`quiz_answers` are written live by the FastAPI app
  in response to bot traffic, not by an ingestor batch pipeline — the
  ingestor's `*StoreRepository` convention doesn't fit. Follows the existing
  `@repository` convention already used by `QuizQuestionRepository` and
  friends (see Feasibility Evidence).
- **Rejected alternatives:** a shared repository under
  `src/commons/repositories/db/` — rejected as premature (YAGNI); nothing
  today needs the ingestor or another component to read/write these tables.

### AD-10: DB access reuses sync `PostgresClient` + `asyncio.to_thread`, no new async client
- **Rationale:** matches the pattern every existing `guidami_ai_patente`
  repository already follows (AD-25, see `QuizQuestionRepository`'s own
  docstring) — the new repository's methods stay synchronous internally,
  wrapped in `asyncio.to_thread` at the router boundary, while the calling
  `AsyncUseCase`/service stays `async` end-to-end.
- **Rejected alternatives:** a dedicated async Postgres client
  (`AsyncConnection`/`AsyncConnectionPool`) — a new, undecided subsystem for
  one non-performance-critical use case.

### AD-11: `/start` and `/quiz` are split into two distinct handlers; `GET /me` backs only `/start`'s greeting
Spec 0015 registered one handler, `start_or_quiz`, for both `/start` and
`/quiz` (`CommandHandler(["start", "quiz"], start_or_quiz)`,
`src/guidami_ai_patente_bot/main.py:56`), which unconditionally proposed a
question. This spec splits them: `/start` calls `GET /me` and only shows a
status message (FR-7); `/quiz` keeps proposing a question via its unchanged
resume-if-pending logic (FR-8) and never calls `GET /me`.
- **Rationale:** the user decided `/quiz` should mean "play" (an action),
  while `/start` means "check my status" (an information request) — two
  different intents that happened to share one handler by accident in spec
  0015's MVP scope, not by design. The user explicitly wants a
  differentiated "benvenuto" vs. "richiesta in attesa di approvazione"
  message on `/start` (FR-2, FR-7), rather than the generic 403 fallback
  text `/quiz` would show an unregistered caller (FR-10) — considered and
  rejected as the simpler alternative (see below).
- **Rejected alternatives:** keeping the single `start_or_quiz` handler and
  relying solely on the generic 403 message for an unregistered user's very
  first `/start`/`/quiz` (no `GET /me`, no dependency-splitting) — simpler,
  explicitly considered, rejected by the user in favor of the nicer
  first-contact UX; keeping one shared handler but branching internally on
  which command name triggered it — rejected once `/quiz` gained its own
  distinct "begin playing" identity (D-13), since `/start` genuinely never
  proposes a question anymore and `/quiz` genuinely never checks status.

### AD-12: Bot↔backend trust relies on network isolation, not a shared secret — documented as a load-bearing assumption
`X-Telegram-User-Id` carries no credential; anyone who can reach the FastAPI
app directly could set it to any value and impersonate a `registered=true`
user, bypassing Telegram entirely.
- **Rationale:** the user confirmed the backend is reachable only by the bot
  today (private network/localhost), consistent with the bot's own default
  `api_base_url = "http://localhost:8000"` — so no additional secret is
  needed now, keeping the design simple as prioritized throughout.
- **Caveat:** `AppConfig.host` defaults to `"0.0.0.0"` (all interfaces) —
  the app's own default binding does not itself guarantee private-only
  reachability; that is a deployment/firewall matter outside this design.
- **Revisit trigger:** if the backend's deployment ever becomes reachable
  from anywhere other than the bot, this decision must be revisited before
  shipping that change — the documented fallback is a second header (e.g.
  `X-Bot-Api-Key`) carrying a shared secret, checked before the declared
  `X-Telegram-User-Id` is ever trusted.

### AD-13: `QuizApiClient` threads a `telegram_user_id` through every public method; `_request` attaches the header once
- **Rationale:** `_request` is already the single chokepoint every public
  method (`propose_question`, `download_image`, `check_answer`,
  `get_explanation`) funnels through — the right place to attach
  `X-Telegram-User-Id` exactly once rather than at each call site. Each
  public method gains a `telegram_user_id: int` parameter, sourced by every
  handler from `update.effective_user.id` and threaded through
  `QuizFlowService`. `check_answer` additionally gains a `session_id: str`
  parameter (the active `QuizSession.seed`, D-12) to populate FR-5's new
  `quiz_answers` row. Two new public methods join the four existing ones:
  `check_registration_status(telegram_user_id) -> bool` (`GET /me`, FR-2)
  and `get_session_summary(telegram_user_id, session_id) ->
  SessionSummary` (the new endpoint, AD-16, FR-9).
- **Rejected alternatives:** a `QuizApiClient`-level mutable "current user"
  field set before each call — implicit, easy to leave stale between
  concurrent updates; an `httpx` event hook reading some ambient context —
  more machinery than the explicit-parameter approach for no real benefit
  here.

### AD-14: New `AppConfig` fields `users_table`/`quiz_answers_table`, following the existing table-name-as-config convention
- **Rationale:** every existing table name is already sourced from an
  `AppConfig` field (`quiz_questions_table`, `quiz_images_table`, ...) rather
  than hardcoded in repository SQL — the new repository follows the same
  convention rather than introducing a hardcoded exception.

### AD-15: Whether the auth mechanism composes with pywire's `Autowired[T]` route-parameter resolution is confirmed by the implementation plan, not fixed here
Every route in `guidami_ai_patente/api/routers/quiz_questions.py` today
takes only plain path/query parameters plus bare `Autowired[T]` parameters —
no `Depends()` appears anywhere in the existing routers. Whether
`require_registered_user`/the base identity step is implemented as an
ordinary FastAPI `Depends()` function that itself resolves a pywire
`@repository` via `get_default_container()`, or some other mechanism pywire
supports, is left open.
- **Rationale:** mirrors the precedent spec 0015 set for its own
  DI-mechanism uncertainty (AD-8: "whether python-telegram-bot's
  handler-registration model supports bare `Autowired[T]` handler parameters
  ... is left for the implementation plan to confirm against pywire's actual
  API") — resolving it here would guess at pywire internals not yet
  exercised for this shape of dependency (a per-request guard, not a
  singleton component).

### AD-16: New endpoint reports a session's answered/correct counts, gated like every other business endpoint
A new endpoint (exact path/shape left for the implementation plan, e.g.
`GET /quiz-answers/summary?session_id=...`) takes the caller's
`X-Telegram-User-Id` and a `session_id`, and returns how many `quiz_answers`
rows exist for that `(user_id, session_id)` pair and how many are correct.
- **Rationale:** backs `/stop`'s summary (FR-9/D-15). Correctness is
  computed via the same `JOIN` against `quiz_questions.correct_answer` every
  other correctness check in this spec uses (AD-3) — never a stored,
  potentially-stale `is_correct`. Gated by `require_registered_user` (AD-8)
  like every other business endpoint; scoped by both `user_id` and
  `session_id` so one user can never read another user's session summary by
  guessing/reusing a `session_id`.
- **Rejected alternatives:** computing the summary bot-side by having the
  bot fetch every individual `quiz_answers` row and aggregate locally —
  rejected as pointless extra data transfer and business logic leaking into
  the bot for a plain aggregate query the database already does well.

## Data Model

Two new tables added to `db/init.sql` (see AD-2/AD-3 for full DDL and
rationale), plus two new `AppConfig` fields (AD-14):

```python
users_table: str = "users"
quiz_answers_table: str = "quiz_answers"
```

Per the project's entity convention, DB-generated columns are omitted from
the corresponding entity: `users`'s entity (`UserEntity`) carries only
`telegram_user_id`/`registered` (`id`/`created_at` are DB-generated and
therefore not entity fields). `quiz_answers` gets **no** entity: `user_id`
and `quiz_id` are surrogate FKs that are never resolved to a Python value
anywhere in this design — the repository resolves both server-side, via a
natural-key subquery inside one `INSERT ... SELECT` (`users.telegram_user_id`,
`quiz_questions.number`), the same style `QuizQuestionRepository.find_by_permutation`
already uses for its own natural-key lookups. The one value ever read back is
the aggregate the summary endpoint needs (AD-16) — `answered`/`correct`
counts — modeled as a plain `SessionSummary` value object, not a row-shaped
entity, since it has no DB row of its own.

No migration tool exists in this project (`db/init.sql` is applied by
recreating the Postgres container from scratch, per `CLAUDE.md`'s
Infrastructure section); the local dev stack needs
`docker compose down && rm -rf docker/.volumes/postgres_data && docker
compose up -d` to pick up the new tables. The ephemeral test stack
(`tmpfs`, never persisted) picks up schema changes automatically on its
next session-scoped start.

## Constraints

- The bot never queries Postgres directly — every read/write of `users`/
  `quiz_answers` goes through the FastAPI backend's HTTP API (hard
  constraint stated by the user).
- `pywire` field-injection conventions (`.claude/rules/pywire-di.md`) are
  followed for any new `@repository`/`@service`; no constructor-parameter
  exception is introduced.
- No new async Postgres client is introduced (AD-10); the sync
  `PostgresClient` + `asyncio.to_thread` pattern is reused as-is.
- No bot-driven approval flow and no admin CLI for flipping `registered` are
  built (Non-Goals) — it stays a manual, out-of-band DB operation.
- Integration tests target only the isolated, ephemeral test Postgres stack
  (`docker/docker-compose.test.yml`) — never the dev database.

## Feasibility Evidence

- **AD-2/AD-3 (FK targets)** — `db/init.sql:46-60` — `quiz_questions.id` is
  `BIGSERIAL PRIMARY KEY` (line 47), `UNIQUE(number)` (line 59); confirms
  `quiz_answers.quiz_id -> quiz_questions(id)` targets a real surrogate
  column distinct from the `number` natural key (verified 2026-09-17).
- **AD-4/AD-15 (no existing `Depends()` precedent)** —
  `src/guidami_ai_patente/api/routers/quiz_questions.py:1-92` — every route
  takes only plain path/query params plus bare `Autowired[T]` parameters; no
  `Depends()` appears anywhere in this file (verified 2026-09-17).
- **AD-9 (repository convention)** —
  `src/guidami_ai_patente/repositories/quiz_question_repository.py:1-33` —
  existing `@repository` pattern (`Autowired[AppConfig]`,
  `Autowired[PostgresClientProvider]`) the new repository follows (verified
  2026-09-17).
- **AD-10 (sync + `asyncio.to_thread`)** — same file, docstring lines 24-28:
  "Synchronous by construction: psycopg is, and the routers cross the
  boundary with `asyncio.to_thread` (AD-25)" (verified 2026-09-17).
- **AD-12 (network defaults)** —
  `src/guidami_ai_patente/configs/app_config.py:37-38` (`host: str =
  "0.0.0.0"`, `port: int = 8000`); `src/guidami_ai_patente_bot/configs/
  bot_config.py:22` (`api_base_url: str = "http://localhost:8000"`)
  (verified 2026-09-17).
- **AD-13 (`_request` chokepoint)** —
  `src/guidami_ai_patente_bot/clients/quiz_api_client.py:48-81` — every
  public method (`propose_question`, `download_image`, `check_answer`,
  `get_explanation`) already funnels through the single `_request` method;
  none currently takes or forwards any user-identifying parameter (verified
  2026-09-17).
- **AD-14 (table-name-as-config convention)** —
  `src/guidami_ai_patente/configs/app_config.py:52-59` — every existing
  table name is a config field (`quiz_questions_table`, `quiz_images_table`,
  ...), never hardcoded in repository SQL (verified 2026-09-17).
- **AD-11 (`/start`/`/quiz` share one handler today, to be split)** —
  `src/guidami_ai_patente_bot/main.py:56` —
  `CommandHandler(["start", "quiz"], start_or_quiz)`;
  `src/guidami_ai_patente_bot/handlers/quiz_handlers.py:66-69` —
  `start_or_quiz` calls `_send_question` unconditionally, which calls the
  `require_registered_user`-gated `GET /quiz-questions/random` immediately;
  confirms both the starting point AD-11 splits apart and that `/quiz`'s own
  resume-if-pending logic (`_send_question`'s `session: QuizSession | None
  = context.user_data.get("session")`, line 48) is untouched by that split
  (verified 2026-09-17).
- **FR-9/D-16 (stale button after `/stop` already fails safely)** —
  `src/guidami_ai_patente_bot/services/quiz_flow_service.py:53-54` —
  `handle_answer` raises `StaleQuestionError` whenever `session is None`,
  exactly the state `/stop` leaves `context.user_data` in — no new stale-
  guard code is needed for this interaction (verified 2026-09-17).

## Definition of Done

- `db/init.sql` updated with the `users`/`quiz_answers` tables and indexes
  (AD-2/AD-3); local dev Postgres recreated to pick up the schema.
- New `UserEntity` and repositories for `users`/`quiz_answers` in
  `guidami_ai_patente/`, following the existing `@repository`/`AppConfig`
  conventions (AD-9/AD-10/AD-14) — `quiz_answers` gets no entity (see Data
  Model) — integration-tested against the ephemeral test stack, matching the
  codebase's existing thin-repository convention (`QuizQuestionRepository`,
  `GoldenSetReadRepository`: integration-only, no unit-test double, since
  there is no branching logic to isolate beyond what the integration test
  already covers end to end).
- The base identity-resolution step and `require_registered_user` (AD-4)
  are implemented and integration-tested: an unregistered
  `X-Telegram-User-Id` gets 403 on a protected endpoint and 200 with
  `registered: false` on `GET /me`; a registered one passes through
  unchanged.
- `POST /quiz-questions/{number}/check` integration-tested to confirm a
  `quiz_answers` row is written (including `session_id`) alongside the
  unchanged graded response (FR-5).
- The new session-summary endpoint (AD-16) integration-tested: correct
  answered/correct counts for a session with a mix of correct/incorrect
  answers, and a zero/zero result for a session with none yet (FR-9).
- `QuizApiClient` integration/unit-tested to confirm `X-Telegram-User-Id` is
  attached on every call (FR-6), and that `check_answer` forwards
  `session_id`.
- `/start` is its own handler, calls `GET /me` first, and branches per FR-7
  without ever proposing a question; `/quiz` is a separate handler, and a
  regression test confirms its resume/fresh session logic (FR-8) still
  behaves exactly as spec 0015 specified, now reachable independently of
  `/start`; the generic-403 message (FR-10) is covered by a handler-level
  test extending spec 0015's existing error-path test.
- `/stop` integration/handler-tested: shows the correct summary and clears
  the session when one exists (FR-9); shows "nessuna sessione in corso" and
  makes no backend call when one doesn't.
- A manual Telegram session confirms: an unapproved user sees the
  "in attesa di approvazione" message on `/start` and a 403-driven generic
  message on `/quiz`; after the owner manually sets `registered = true`,
  the same user can play via `/quiz` and end with `/stop` to see a correct
  summary, and their answers appear in `quiz_answers` with the right
  `session_id`.
- `uv run ruff check`, `uv run ruff format --check`, and `uv run pyright`
  pass.
- `docs/second-brain/` updated (new tables in `database.md`, new
  endpoints/dependency mechanism in `architecture.md`, any new pattern in
  `patterns.md`/`.claude/rules/pywire-di.md` if AD-15 resolves to a new
  documented convention) before this branch is pushed, per the repo's
  Second Brain gate.

## Open Questions

- [x] **non-blocking** — AD-15: the concrete mechanism for
  `require_registered_user`/the base identity step (plain `Depends()` vs.
  another pywire-compatible shape) — owner: whoever extracts the
  implementation plan, to confirm against pywire's actual API before
  writing route code.
  **Resolved** by the backend plan (Task 3): ordinary FastAPI `Depends()`
  functions, not pywire components — `require_registered_user` depends on
  `resolve_identity`, which depends on a small hand-written `_get_user_repository`
  `Depends()` step resolving `UserRepository` via the same container fallback
  pywire's own `_resolve_autowired` uses internally
  (`getattr(request.app.state, "pywire_container", None) or get_default_container()`).
- [x] **non-blocking** — the new session-summary endpoint's exact path and
  response JSON shape (AD-16) — owner: implementation plan.
  **Resolved** by the backend plan (Task 7): `GET /quiz-answers/summary?session_id=...`
  → `{"answered": int, "correct": int}`.

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by write-spec on 2026-09-17, based on
  Feasibility Evidence above.
