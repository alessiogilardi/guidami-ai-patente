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

# Spec 0018: Explanation translation (IT→RU)

| | |
|---|---|
| **Id** | 0018 |
| **Status** | ready |
| **Date** | 2026-09-18 |
| **Discussion log** | — (brainstormed inline via `superpowers:brainstorming`, then stress-tested via `mattpocock-skills:grilling`; no separate transcript file) |
| **Supersedes / superseded by** | — |

## Problem & Motivation

The quiz explanation (`GET /quiz-questions/{number}/explanation`, spec 0013,
narrowed by spec 0017) is only ever produced in Italian:
`ExplanationWriterAgent`'s prompt and the corpus normativo it grounds on are
both Italian. Russian-speaking users of the Telegram bot need the same
explanation in Russian.

The user explicitly decided **translation over dual-language generation**:
translate the already-produced Italian explanation with a dedicated LLM
agent, rather than having `ExplanationWriterAgent` (or a Russian sibling of
it) generate the explanation directly in Russian. This keeps the RAG/judge
pipeline single-language and untouched — the thing that actually needs to
reason over the Italian corpus normativo never has to do so in a second
language — and confines the new work to a narrow, independent translation
step.

Reaching this design took several rejected intermediate shapes, discussed
and discarded during brainstorming/grilling (recorded here since they are
the kind of thing a future reader would otherwise re-propose):

- **Generating the explanation directly in Russian** — rejected by the
  user's own framing of the request: it would duplicate the writer
  agent/prompt per target language and couple translation quality to the
  RAG pipeline itself, instead of isolating it.
- **A generic, upfront multi-language design** (an agent parameterized over
  an arbitrary target language, DTOs shaped for N languages) — rejected as
  premature: only IT→RU is needed today (YAGNI); a second language, if it
  ever arrives, extends this design rather than requiring one purpose-built
  for it.
- **Nesting the endpoint under `/quiz-questions/{number}/explanation/translate`**
  — rejected once grilling surfaced that `{number}` would be a dead path
  parameter: every existing route that takes `{number}` in its path
  validates it against the DB and 404s on a miss (`/check`, `/explanation`,
  `/label` — see Feasibility Evidence), but this endpoint has no use for the
  row at all, since the client already holds the translatable text. Keeping
  `{number}` unused-and-unvalidated would either silently break that
  convention or force a pointless extra DB read just to keep it. Removing
  the path parameter entirely resolves the tension.
- **The endpoint re-invoking the whole explanation pipeline internally**
  (accepting `submitted`/`number` and calling `ExplanationService` itself
  before translating) — rejected: it would re-pay the judge/writer LLM cost
  on every translation call and re-couple a decoupled concern. The client
  already has the Italian text from its own prior `GET /explanation` call
  and passes it directly in the request body.
- **Caching translations in the database** (mirroring the golden-set
  explanation cache) — rejected for now: adds schema and invalidation
  complexity with no demonstrated need; translations are computed live on
  every call.
- **An `output_validator` checking normative-reference fidelity** (mirroring
  `CommaLabelerAgent`'s ordinal-range validator) — rejected: fidelity to
  article/comma numbers and proper nouns is enforced through explicit prompt
  instructions only, consistent with how every agent in this codebase except
  `CommaLabelerAgent` operates; no precedent or demonstrated failure mode
  justifies the extra machinery yet.
- **Injecting a curated IT→RU domain glossary into the prompt** — rejected:
  a well-specified system prompt (translator specialized in Italian traffic
  law/driving-exam language, formal register, official Russian road-safety
  terminology, normative references and proper nouns left untouched) is
  judged sufficient; no glossary resource exists or is built for this spec.
- **A dedicated `TranslationUnavailableError`** — rejected after re-reading
  `docs/superpowers/plans/2026-09-18-on-demand-explanation.md`'s Task 5:
  `LabelingService` reuses the existing `ExplanationUnavailableError` for
  its own timeout/failure case rather than minting a new exception, because
  the *meaning* (an LLM-backed stage of the explanation feature failed or
  timed out → 503) is identical, not merely similar. Translation failure is
  the same meaning, so it reuses the same exception (AD-4).
- **Bot-side integration** (a "Traduci in russo" button, keyboard/message
  changes) — explicitly deferred by the user to a later spec; this spec is
  API-only.

## Functional Requirements

### FR-1: `POST /explanations/translate?lang=ru` translates a given explanation text to Russian

New endpoint, its own router (not nested under `/quiz-questions/{number}`,
per the rejected alternative above). Request body: `{"text": str}`, the
Italian text to translate — the client obtains it beforehand from `GET
/quiz-questions/{number}/explanation` and passes it verbatim; the endpoint
never re-reads or recomputes it. Response body: `{"translated_text": str}`.

### FR-2: Only `lang=ru` is accepted today

Any other value for the `lang` query parameter is rejected with `400`. The
parameter exists on the URL for forward compatibility, but no other
language is implemented (see Non-Goals).

### FR-3: The input text is bounded

The request DTO's `text` field carries `max_length=6000` characters. A
request whose `text` exceeds this, or omits it, is rejected with `422`
(standard Pydantic validation) — never silently truncated.

### FR-4: The endpoint requires the same authentication as its sibling quiz endpoints

`POST /explanations/translate` depends on `_RequireRegisteredUser`
(`src/guidami_ai_patente/api/dependencies/user_identity.py`), exactly like
`/check`, `/explanation`, `/label`, `/random`. An unregistered caller gets
`403` via the existing global exception boundary
(`UnregisteredUserError` → `_forbidden`, `exception_handlers.py`) — no new
auth wiring.

### FR-5: The translation is produced by a domain-specialized agent, not a generic translator

`ExplanationTranslatorAgent`'s system prompt instructs the model to act as a
translator specialized in Italian traffic law and driving-exam language
(Codice della Strada / Codice delle Assicurazioni Private register),
targeting the terminology a Russian driving-exam candidate would recognize
— not a generic "translate this text" instruction. The prompt explicitly
requires normative references (article/comma numbers, e.g. "art. 141 CdS")
and proper nouns of the code (e.g. "Codice della Strada") to be preserved
verbatim, never translated or reworded.

### FR-6: No persistence

The translation is computed live on every call. No new table, no column, no
cache — a repeated call with the same text pays the LLM cost again.

### FR-7: A translation failure or timeout is a `503`

The agent call runs under `AppConfig.translation_deadline_s` (default
`20.0`, AD-5). On `TimeoutError` or any agent-call failure, the endpoint
raises the existing `ExplanationUnavailableError` (AD-4), mapped to `503` by
the already-registered `_service_unavailable` handler — no new exception
class, no new handler registration.

## Non-Goals

- No generic or multi-language-parameterized translation design — only
  IT→RU, per the user's explicit YAGNI call.
- No bot-side UI/consumer changes (button, keyboard, message rendering) —
  deferred to a later spec.
- No database caching or persistence of translations.
- No `output_validator`-style automated fidelity check on normative
  references — prompt instructions only (FR-5).
- No curated glossary resource injected into the prompt. **Superseded** by FR-8/AD-9
  below (2026-09-22 amendment, driven by spec 0020): a caller may now inject specific
  term hints, though still no standing glossary resource is *owned* by this spec.
- No rate limiting beyond the existing per-request `max_length` bound
  (FR-3) — consistent with every other endpoint in this API today, none of
  which rate-limit per user.
- No change to `GET /quiz-questions/{number}/explanation`, `/check`,
  `/label`, or any other existing endpoint.

## Architectural Decisions

### AD-1: A decoupled, dedicated endpoint with no `{number}` path parameter

`POST /explanations/translate?lang=ru` lives in its own router
(`api/routers/explanation_translations.py`, AD-2), separate from
`quiz_questions.py`. It takes no `{number}`: the text to translate arrives
in the request body, and every existing route that *does* take `{number}`
validates it against the DB and 404s on a miss (`QuizAnswerChecker`,
`ExplanationService`, `LabelingService` — see Feasibility Evidence). Since
this endpoint has no use for the row, keeping an unused, unvalidated
`{number}` in the path would either misrepresent that convention or force a
pointless DB read purely to satisfy it; omitting it entirely is the
consistent choice.

### AD-2: New router, not an addition to `quiz_questions.py`

Translation is not a per-question operation (AD-1), so it does not belong
in the router keyed on `{number}`. A new router file keeps
`quiz_questions.py` untouched by this spec — no merge surface with the
concurrent work in `docs/superpowers/plans/2026-09-18-on-demand-explanation.md`,
which modifies that same file (Task 6).

### AD-3: `ExplanationTranslatorAgent` mirrors `ExplanationWriterAgent`'s wiring exactly

Same shape as the existing agent
(`src/guidami_ai_patente/agents/explanation_writer/explanation_writer_agent.py`):
pywire `@agent` decorator, `BaseAgent[ExplanationTranslationRequest, ExplanationTranslationResponse]`,
`output_type = ExplanationTranslationResponse`, and three `Autowired` fields
— `AgentConfigRepository`, `OpenRouterProviderComponent`,
`LlmCallTrackerProvider` — with a zero-arg `__init__` calling
`super().__init__(config=..., provider=..., tracker=...)`. The
`LlmCallTrackerProvider` wiring is not optional: ADR 0031 requires every
API-side agent to report through the shared tracker.

### AD-4: Reuse `ExplanationUnavailableError`, no new exception class

`LabelingService` (the concurrent spec 0017 plan, Task 5) raises the
existing `ExplanationUnavailableError` for its own timeout/failure case
rather than introducing a new exception — the established pattern in this
codebase is: a new exception class is minted only when the *meaning*/status
differs (as `LabelingNotReadyError`'s `409` does from a `503`), not merely
when the component differs. Translation failure carries the same meaning
("an LLM-backed stage of the explanation feature failed or timed out"), so
it raises the same `ExplanationUnavailableError`, already mapped to `503`.

### AD-5: `translation_deadline_s` defaults to `20.0`

The concurrent spec 0017 plan (`docs/superpowers/plans/2026-09-18-on-demand-explanation.md`)
has since merged, narrowing `AppConfig.explanation_deadline_s` to a writer-stage-only
budget; a follow-up commit (`ebea2c0e`, "Raise explanation_deadline_s to 20s for retry
headroom") then raised it from that plan's original `10.0` to its current `20.0` on
`main` — not `10.0` as this AD originally assumed when drafted. The translator is
likewise a single LLM call, but with `max_tokens: 2400` (AD-6, 4x the writer's
`600`), so its own deadline is also set to `20.0`: the same order of magnitude as
`explanation_deadline_s` rather than a multiple of it — both cover one round trip
plus pydantic-ai's own validation retries, and no measured production latency data
exists yet to justify a wider margin for the translator specifically.

### AD-6: Input/output size bounded, doubled from the initial proposal for safety margin

`ExplanationTranslationRequest.text` carries `max_length=6000` characters;
`ExplanationTranslatorAgent`'s config sets `max_tokens=2400`. Both are
roughly double the values initially proposed (3000 chars / 1200 tokens),
per the user's explicit request for extra safety margin. For scale: sibling
agents' `max_tokens` are `explanation_writer: 600`, `comma_labeler: 700`,
`retrieval_judge: 500` (`configs/agents/*.yaml`) — all short structured
outputs. The translator's ceiling is set higher because Cyrillic text
generally tokenizes less efficiently than the Italian source for
equivalent content, and because no existing convention caps request-body
text length in this API (see Feasibility Evidence) — this spec introduces
that convention for this endpoint specifically, not as a repo-wide rule.

### AD-7: Specialization lives entirely in the prompt

No RAG, no injected glossary, no `output_validator` (see Non-Goals and the
rejected alternatives above). `ExplanationTranslatorAgent`'s prompt alone
carries the domain specialization (FR-5) and the reference-preservation
instruction. This matches how every agent in the codebase behaves except
`CommaLabelerAgent`, whose validator checks a structurally different kind
of failure (an out-of-range ordinal, mechanically checkable) than
translation fidelity (not mechanically checkable without a second model
call, which is out of scope here).

### AD-8: Response and request DTO language follow the existing agent-DTO convention

`ExplanationTranslationResponse`'s class docstring and
`Field(description=...)` are written in Italian, per
`.claude/rules/code-conventions.md`'s documented exception: this schema is
shipped to the LLM by `pydantic_ai` as the output/tool description, so it
is prompt content, not code documentation — independent of the fact that
the *content* it describes (`translated_text`) is Russian.
`ExplanationTranslationRequest`'s docstring stays English, since it is
never shipped to the model as schema.

### FR-8: Optional translation hints anchor specific terms (amendment, driven by spec 0020)

The request gains an optional field: `hints: list[TranslationHint] = []`
(`TranslationHint = {"term": str, "term_ru": str}`), bounded `max_length=10`, each
`term`/`term_ru` `max_length=80`. When present, the agent's prompt instructs it to
render every occurrence of `term` in `text` using `term_ru` as the word choice
(grammatically inflected into the sentence as Russian requires — case, number — never
substituted with a different word), and, on the term's first occurrence only, to show
it paired with the Italian original in guillemets: `«TERMINE» (rendering)`, mirroring
the existing "Vero"/"Falso" convention already in the system prompt.

This lets a caller that already owns a reviewed, authoritative translation for a
specific term (spec 0020's glossary, spec 0019) guarantee the same Russian rendering
appears every time that term is translated, instead of leaving the model to infer it
fresh, and possibly inconsistently, on every call. A request with no `hints` behaves
exactly as before — this is a backward-compatible addition, not a behavior change to
the existing contract.

### AD-9: Hints are advisory-authoritative, never a verbatim substitution

`hints` bounds the *choice* of Russian word, not its exact surface form: the agent
still inflects it into the sentence's grammatical case, as a human translator would
use a dictionary entry. This is deliberately different from the exact-substring
verbatim rule spec 0019's extractor `output_validator` enforces on Italian legal text
— Russian's case system would make a rigid substitution produce ungrammatical output.
Fidelity to a hint is therefore left to the prompt, not a mechanical validator,
consistent with FR-5's "prompt-only fidelity" precedent for every agent in this
codebase except `CommaLabelerAgent`.

## Data Model

No schema changes to this feature's own scope. No new tables, columns, or migrations
are introduced *here*; `hints` is request-only data, never persisted. (Spec 0019
separately adds a `term_ru` column to its own `glossary_entries` table, to have
something to pass as a hint — that table is not this spec's concern.)

## Constraints

- pywire field-injection conventions (`.claude/rules/pywire-di.md`) apply
  to the new agent, service, and router dependency exactly as they do to
  `ExplanationWriterAgent`/`ExplanationService`.
- Router bodies stay thin controllers — no `try/except`, no status-code
  logic in the new router file (existing convention, e.g.
  `quiz_questions.py`).
- `AGENTS_DIR`/`AppConfig.agents_dir` already resolves the directory a new
  `configs/agents/explanation_translator.yaml` must live in — no new
  configuration root (AD-22/AD-27, spec 0012).
- Every `UseCase`/`AsyncUseCase` is invoked via `__call__`, never
  `.execute()` directly (`.claude/rules/use-case-invocation.md`) — applies
  to the new `ExplanationTranslationService`.
- One class per file (`~/.claude/rules/python/architecture.md`).
- Logging: lazy `%s`/`%r` args, never f-strings (`.claude/rules/logging.md`).

## Feasibility Evidence

- **AD-1** — supported by: `src/guidami_ai_patente/services/quiz_answer_checker.py:34-36` and
  `src/guidami_ai_patente/services/explanation_service.py:79-81` — both resolve `{number}` via a
  repository call and raise `QuestionNotFoundError` (mapped to `404`,
  `exception_handlers.py:66`) on a miss, confirming the "every route with
  `{number}` validates it" convention this spec deliberately does not
  extend to an endpoint with no use for the row (verified 2026-09-18).
- **AD-3** — supported by: `src/guidami_ai_patente/agents/explanation_writer/explanation_writer_agent.py`
  (full 44-line file quoted during grilling) — the exact pywire `@agent` +
  `Autowired[AgentConfigRepository, OpenRouterProviderComponent, LlmCallTrackerProvider]`
  shape `ExplanationTranslatorAgent` mirrors (verified 2026-09-18).
- **AD-3** — supported by: `docs/second-brain/adr/0031-api-side-llm-call-tracking-via-pre-destroy.md`
  and `src/guidami_ai_patente/providers/llm_call_tracker_provider.py:14,37-51` — confirms
  `LlmCallTrackerProvider` wiring is mandatory for every API-side agent, not
  optional instrumentation (verified 2026-09-18).
- **AD-4** — supported by: `docs/superpowers/plans/2026-09-18-on-demand-explanation.md`, Task 5
  (`LabelingService.execute`) — raises the existing `ExplanationUnavailableError`
  for its own timeout, rather than a new exception, the precedent this
  spec's AD-4 follows (verified 2026-09-18).
- **AD-5** — supported by: `src/guidami_ai_patente/configs/app_config.py:62-86` — the
  `on-demand-explanation` plan has since merged and split the old combined budget into
  `labeling_deadline_s: float = Field(default=25.0, ...)` (retrieval+judge stage) and
  `explanation_deadline_s: float = Field(default=20.0, ...)` (writer stage only, raised
  from that plan's original `10.0` by a follow-up commit, `ebea2c0e`) — both confirmed
  present on `main` at their current values (re-verified 2026-09-20).
- **AD-6** — supported by: `configs/agents/explanation_writer.yaml:2-4` (`max_tokens: 600`),
  `configs/agents/comma_labeler.yaml:4` (`max_tokens: 700`),
  `configs/agents/retrieval_judge.yaml:4` (`max_tokens: 500`) — the comparison
  set for the translator's `max_tokens: 2400` (verified 2026-09-18).
- **AD-6** — supported by: a repo-wide grep for `max_length` under
  `src/guidami_ai_patente/` returning zero matches on any inbound FastAPI
  request DTO (all existing `max_length` occurrences are on agent
  input/output DTOs, e.g. `explanation_writer_response.py:19-20,27-28`) —
  confirms this spec introduces the convention of a bounded request-body
  text field for this endpoint, not an extension of an existing one
  (verified 2026-09-18).
- **FR-4** — supported by: `src/guidami_ai_patente/api/dependencies/user_identity.py:39-58`
  (`resolve_identity`/`require_registered_user`) and
  `src/guidami_ai_patente/api/routers/quiz_questions.py:22`
  (`_RequireRegisteredUser` used on every route) — the auth dependency this
  spec's FR-4 reuses unchanged (verified 2026-09-18).
- **FR-7** — supported by: `src/guidami_ai_patente/api/exception_handlers.py`
  (`_service_unavailable`, `ExplanationUnavailableError` registration) —
  the existing `503` mapping this spec reuses with no new handler
  (verified 2026-09-18).

## Open Questions

- [ ] **non-blocking** — exact router file/module name
  (`api/routers/explanation_translations.py` proposed, AD-2) — left to
  implementation.
- [ ] **non-blocking** — exact prompt text for `ExplanationTranslatorAgent`
  (FR-5's specialization and reference-preservation instructions) — left to
  implementation.
- [ ] **non-blocking** — whether an `@pytest.mark.integration` test against
  the real LLM is added for this agent, mirroring any existing equivalent
  for `ExplanationWriterAgent` — left to implementation to confirm the
  precedent and follow it.

## Sign-off

- **Scope approved by user:** approved 2026-09-22 (FR-8/AD-9, the only remaining
  scope — FR-1 through FR-7 were already implemented and shipped before this
  amendment)
- **Feasibility asserted:** by the assistant on 2026-09-18, based on
  Feasibility Evidence above (source reads via dispatched research
  subagents, not a dedicated feasibility-compiling skill)

## Changelog

- **2026-09-22** — Amended for spec 0020: added the optional `hints` field (FR-8,
  AD-9) so a caller can anchor a specific term to an already-reviewed translation
  instead of leaving the model to infer it fresh every call. Backward-compatible: a
  request with no `hints` is unaffected. Marked the "no curated glossary resource"
  Non-Goal as superseded by this amendment.
- **2026-09-18** — Initial draft, from an interactive `superpowers:brainstorming`
  session (endpoint shape, no caching, `503` on failure, prompt-only
  reference fidelity).
- **2026-09-18** — Amended after a `mattpocock-skills:grilling` round:
  dropped `{number}` from the path entirely (AD-1), moved to a dedicated
  router (AD-2), doubled `max_length`/`max_tokens` for safety margin (AD-6).
- **2026-09-18** — Amended after revalidating against the concurrent
  `docs/superpowers/plans/2026-09-18-on-demand-explanation.md` plan: reuse
  `ExplanationUnavailableError` instead of a new exception class (AD-4),
  and recalibrated `translation_deadline_s` from `30.0` to `20.0` against
  the plan's new `explanation_deadline_s=10.0` single-call benchmark (AD-5).
- **2026-09-20** — Corrected AD-5 and its Feasibility Evidence: the
  `on-demand-explanation` plan has since merged, and a follow-up commit
  (`ebea2c0e`) raised `explanation_deadline_s` from that plan's `10.0` to
  `20.0` on `main`. `translation_deadline_s`'s own value (`20.0`) is
  unchanged; only the now-false "2x" rationale was corrected to "same order
  of magnitude." Found while verifying the downstream implementation plan's
  feasibility against current `main`.
