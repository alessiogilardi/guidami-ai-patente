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

# Spec 0015: Telegram bot client (MVP)

| | |
|---|---|
| **Id** | 0015 |
| **Status** | draft |
| **Date** | 2026-09-15 |
| **Discussion log** | — |
| **Supersedes / superseded by** | — |

## Problem & Motivation

The FastAPI app (`src/guidami_ai_patente/`) already serves the full quiz loop —
propose a question, check an answer, fetch its image, get a RAG-backed
explanation — but nothing lets a real user drive that loop today. The only way
to exercise it is to call the endpoints directly (curl/Postman). This spec
covers the first user-facing client: a Telegram bot that presents a question,
takes the user's true/false answer, and shows the outcome plus its
explanation.

This is deliberately scoped as an **initial, minimal iteration**. The
functional requirements below are the smallest slice that gets a real user
through question → answer → explanation on Telegram; topic selection,
persistence across bot restarts, and any richer UX are explicit non-goals for
this pass and are expected to reshape this spec (or be superseded by a new
one) once this MVP is used and reviewed.

## Functional Requirements

### FR-1: Start/request a question

Given a user sends `/start` or `/quiz` to the bot, the bot proposes a random
quiz question addressed to that chat, unfiltered by topic.

**Acceptance criteria:**
- Given a chat with no prior session, when the user sends `/quiz`, then the
  bot calls `GET /quiz-questions/random` with a freshly generated `seed` and
  `index=0`, and sends the question text as a chat message.
- Given the question has no associated image, the bot sends a plain text
  message.
- Given the question has an associated image, the bot downloads it via
  `GET /quiz-images/{filename}` and sends it as a photo with the question
  text as caption.
- The message includes two inline buttons, "Vero" and "Falso".
- Given a chat with an existing session, when the user sends `/quiz` again
  (without having answered the pending question), the same `seed` is reused
  and `index` advances by one, proposing a different question from the same
  seeded permutation.

### FR-2: Answer via inline button

Given a proposed question is on screen, when the user taps "Vero" or "Falso",
the bot checks the submitted answer and shows its explanation in the same
turn.

**Acceptance criteria:**
- The bot calls `POST /quiz-questions/{number}/check` with the tapped
  boolean, then `GET /quiz-questions/{number}/explanation?submitted=` with
  the same boolean.
- The original message (text or photo caption) is edited to show whether the
  answer was correct and the explanation text.
- The inline keyboard is replaced with a single "Prossima domanda ▶" button.
- Given the explanation endpoint reports `insufficient_knowledge`, the bot
  shows the correctness outcome plus a short fallback line stating no
  explanation is available for this question, instead of failing the turn.

### FR-3: Stale button guard

Given a question has already been superseded by a newer one in the same chat,
when the user taps a button belonging to the older message, the bot does not
process it as an answer.

**Acceptance criteria:**
- Each proposed question's callback data encodes its `number`; the bot
  compares it against the chat's current session state before checking the
  answer.
- Given the numbers don't match, the bot answers the callback query with a
  short notice ("Questa domanda non è più valida, usa /quiz") and takes no
  further action.

### FR-4: "Prossima domanda" continues the loop

Given the user taps "Prossima domanda ▶" after seeing an explanation, the bot
proposes the next question in the same seeded permutation, per FR-1's
`index += 1` behavior.

### FR-5: API/network failures surface as a single friendly message

Given a call to the FastAPI backend fails (non-2xx response, timeout, or
connection error), the bot does not crash and does not silently drop the
user's action.

**Acceptance criteria:**
- The failure is logged once, at a single global error boundary
  (`Application.add_error_handler`), with `exc_info=True`.
- If a chat can be identified from the failing update, the bot sends a
  generic Italian error message ("Si è verificato un errore, riprova con
  /quiz") to that chat.

## Non-Goals

- Topic selection/filtering (`GET /quiz-questions/topics` is not consumed in
  this iteration).
- Persisting session state across bot process restarts — state lives only in
  in-memory `context.user_data` for the process lifetime.
- Any authentication, user identity beyond the Telegram `chat_id`, scoring, or
  answer history.
- Webhook-based delivery — the bot runs in long-polling mode only.
- Internationalization — bot-facing strings are Italian only, matching the
  domain content.
- Deployment/process supervision (systemd unit, Docker service, etc.) is out
  of scope for this spec; it covers the application code only.

## Architectural Decisions

### AD-1: Separate process, HTTP-only coupling to the FastAPI app
The bot is a new top-level package (`src/guidami_ai_patente_bot/`), run as its
own process (`uv run telegram-bot`), and talks to `guidami_ai_patente` only
through its public HTTP API (via an internal `QuizApiClient`) — never by
importing its services directly.
- **Rationale:** matches how the other top-level packages in this repo
  (`guidami_ai_patente_ingestor`, `labeling`, `retrieval_evaluation`) are
  already isolated from each other; keeps the bot deployable/scalable
  independently of the API process; reuses the already-tested HTTP contract
  instead of reaching into internal service classes.
- **Alternative rejected:** in-process import of the FastAPI app's services —
  saves a network hop but permanently couples the bot's deployment to the
  API's runtime and internal code shape.

### AD-2: In-memory session state via `context.user_data`
Per-chat state (`seed`, `index`, `current_question_number`) lives in
`python-telegram-bot`'s built-in `context.user_data`, with no persistence
layer.
- **Rationale:** the API is stateless by design; the bot needs to remember
  only enough to render "the next question" and to validate stale button
  taps. A bot restart losing the in-flight question (user re-sends `/quiz`)
  is an acceptable MVP trade-off.
- **Alternative rejected:** `PicklePersistence` or a Postgres-backed session
  table — real infrastructure cost not justified before this MVP has been
  used.

### AD-3: Long polling, not webhook
`Application.run_polling()` — no public HTTPS endpoint, no certificate/reverse
proxy to provision for this iteration.

### AD-4: Plain handlers + `context.user_data`, not `ConversationHandler`
The flow has exactly two logical steps (propose / handle answer), each
re-entrant from `context.user_data` alone. `python-telegram-bot`'s
`ConversationHandler` FSM abstraction is not introduced in this pass.
- **Rationale:** YAGNI — the state machine ceremony (named states,
  entry_points/states/fallbacks) buys nothing for a two-step loop; revisit if
  a later iteration adds topic selection or multi-step settings.

### AD-5: Package layout mirrors existing app conventions
`configs/` (`BotConfig(BaseConfig)`, `frozen=True`, loaded once in
`main.py` — see AD-7), `clients/` (thin `QuizApiClient` httpx adapter, one
method per endpoint shape, pywire `@client` — see AD-8), `models/` (response
DTOs + the `QuizSession` state shape), `services/` (`QuizFlowService` — the
only place with orchestration logic, pywire `@service` — see AD-8),
`handlers/` (thin controllers analogous to FastAPI routes — parse update,
call service, send response, no business logic), `exceptions/`
(`QuizApiError`).
- **Rationale:** consistent with `~/.claude/rules/python/architecture.md`'s
  package-role table and with the "FastAPI routes = thin controllers only"
  rule, applied here to Telegram handlers.

### AD-6: Explanation always shown immediately after checking
No separate "explain" step/button — `check` and `explanation` are both called
in the same turn that handles the button tap, per FR-2.
- **Rationale:** matches the minimal-interaction goal stated by the user;
  avoids an extra conversational round-trip and an extra piece of session
  state to track "has this question been explained yet".

### AD-7: Configuration via `BotConfig(BaseConfig)`, dedicated YAML + env
`configs/bot_config.py::BotConfig` extends
`commons/configs/base_config.py::BaseConfig` — not a bare `BaseSettings`
subclass — inheriting its layered precedence (init > env/.env > YAML,
`settings_customise_sources`) and its `load()` override mechanism. It gets
its own base YAML file (`model_config`'s `yaml_file`) plus env var reads via
`BaseConfig`'s `env_nested_delimiter="__"`/`env_file=".env"`. Fields:
`telegram_bot_token: SecretStr` (no default — a missing token is a loud
`ValidationError` at startup, same posture as `OpenRouterConfig.api_key`),
`api_base_url: str`, `request_timeout_seconds: float`. Loaded once in
`main.py` (never inside a handler/service), then registered on the pywire
container via `register_instance` (AD-8) rather than autowired as if it
constructed itself.
- **Rationale:** matches `BaseConfig`'s own stated purpose ("base class for
  every root, self-loading settings class in the project") and makes
  `BotConfig` the second adopter after `ObservabilityConfig` (ADR 0026),
  continuing that rollout instead of adding a third, bespoke root-config
  shape alongside it.

### AD-8: pywire for the bot's instantiable components (ADR 0032)
`QuizApiClient` is decorated `@client`, `QuizFlowService` is decorated
`@service`; both declare their dependencies as `Autowired[T]` fields — the
same convention `.claude/rules/pywire-di.md` documents for
`guidami_ai_patente`. `BotConfig` is registered as an instance
(`register_instance`), never autowired as a self-constructing component,
mirroring `AppConfig`'s treatment (ADR 0023). Handlers resolve their one or
two dependencies through the container at wiring time in `main.py`; whether
`python-telegram-bot`'s handler-registration model supports bare
`Autowired[T]` handler parameters the way FastAPI routers do, or needs an
explicit `container.resolve(...)` per handler, is left for the
implementation plan to confirm against pywire's actual API outside of a
FastAPI host.
- **Rationale:** ADR 0032 extends pywire's scope (previously
  `guidami_ai_patente`-only per ADR 0015) to this package specifically
  because the bot is a second long-running process with a composition root
  resolved once at startup and components reused across every update — the
  same shape that justified pywire over manual constructor injection for the
  FastAPI app. `commons/` and `guidami_ai_patente_ingestor/` are unaffected.
- **Known, deliberately deferred gap (ADR 0032):** pywire (pinned at
  `v0.8.0`, the latest published tag) has no released support for a
  component that is itself an async context manager. `QuizApiClient`'s
  underlying `httpx.AsyncClient` is therefore closed with an explicit
  `await client.aclose()` in `main.py`'s own shutdown sequence, outside of
  any pywire `@pre_destroy` hook — not a workaround pywire is expected to
  absorb automatically later.

## Definition of Done

- `uv run telegram-bot` starts the bot against a running `guidami_ai_patente`
  instance and a valid bot token.
- A manual Telegram session can complete FR-1 through FR-4 end-to-end.
- `QuizApiClient` and `QuizFlowService` have passing unit tests (TDD,
  `uv run pytest`), with no live Postgres/Telegram dependency.
- `uv run ruff check`, `uv run ruff format --check`, and `uv run pyright`
  pass on the new package.
- `docs/second-brain/` updated (new package in `layout.md`/`architecture.md`,
  and `.claude/rules/pywire-di.md`'s scope statement extended per ADR 0032)
  before this branch is pushed, per the repo's Second Brain gate.
