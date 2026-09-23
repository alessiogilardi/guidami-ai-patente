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

# Spec 0020: Unified "Spiega" — question vocabulary and legal reasoning in one explanation

| | |
|---|---|
| **Id** | 0020 |
| **Status** | draft |
| **Date** | 2026-09-21/22 |
| **Discussion log** | — (brainstormed inline via `superpowers:brainstorming`, then stress-tested via `mattpocock-skills:grilling`; no separate transcript file) |
| **Supersedes / superseded by** | — |
| **Extends** | Spec 0017 (on-demand explanation): this spec adds a second, concurrent stage to the existing `GET /quiz-questions/{number}/explanation`; it introduces no new endpoint |
| **Enhanced by** | Spec 0019 (definition glossary): retrieval degrades gracefully to ungrounded output while its table is empty or absent-but-created (see Independence from Spec 0019) |
| **Enhanced by** | Spec 0018's FR-8/AD-9 amendment (translation hints): improves the fidelity of the *existing* "🇷🇺 Traduci" step when present; the feature works, with lower term-translation consistency, if that amendment is not yet deployed |
| **Companion** | `2026-09-23-question-explanation-flow.md` — non-normative worked-example walkthrough (sequence diagram + concrete payloads) of this spec's request flow; regenerate it if this spec's FR/AD text and that file ever disagree |

## Problem & Motivation

The candidate this feature is for already holds a driving licence, obtained outside
Italy: they know how to drive and how a theory exam works, but not Italian-specific
terms of art ("carreggiata", "banchina") or CdS/CAP-specific rules. Two different
things can block them on a question: not understanding what the Italian sentence
*asks*, and not knowing *why* the correct answer is what it is.

Today the bot's "Spiega" button (spec 0017) answers only the second question — the
legal reasoning behind the correct answer — grounded on judged commas. Nothing
explains the question's own wording. An earlier draft of this spec added a *second*,
separate button and endpoint for that; discussing the shape with the actual user
changed the conclusion: **a candidate wants one explanation, not two**, and reaches for
it at the same moment either way — after seeing whether they got it right. This spec
folds question-vocabulary explanation into the *same* "Spiega" tap, produced by a
second, independent agent, and shown as one message.

Shapes considered and rejected during brainstorming/grilling, recorded so a future
reader does not re-propose them:

- **A separate button and endpoint for question explanation** (this spec's own first
  draft) — rejected after talking to the user: one unified "Spiega" experience serves
  the actual need better than two affordances the user must learn to distinguish and
  tap separately. Dropped along with it: a dedicated `GET
  /quiz-questions/{number}/question-explanation` endpoint, a third bot button, a
  three-keyboard-builder consolidation refactor (no longer needed — the button already
  exists only in the post-answer keyboard), and a dedicated `quiz_question_explanations`
  cache table (see AD-2).
- **One agent doing both jobs** — rejected, per the user's explicit call: vocabulary
  grounding (the glossary, answer-blind) and legal grounding (judged commas, answer-
  aware) are different retrieval contexts with different failure modes; a single
  prompt juggling both is harder to reason about, test and degrade gracefully. Two
  agents, run concurrently, keep each concern narrow — same principle as this
  project's existing judge/writer split (spec 0011, spec 0017).
- **A literal Russian translation of the question** — rejected: it explains nothing
  (no term clarification, no logic of the statement).
- **A simplified-Italian paraphrase** — rejected: independent of any target language,
  and a candidate with weak Italian may not follow it either.
- **Reusing or extending `ExplanationWriterAgent`** for vocabulary too — rejected: its
  prompt and grounding are answer-aware by design (spec 0017); folding in an
  answer-blind concern would blur that.
- **A dedicated per-question cache table for the vocabulary explanation** — rejected:
  the existing legal explanation (spec 0017) is *not* cached (regenerated on every
  `GET /explanation` call, cost already accepted), so caching only the new half would
  be an asymmetric complication for a saving the codebase does not otherwise make.
  Both halves are now generated live, symmetrically (AD-2).
- **General top-k retrieval over the corpus as vocabulary grounding** — rejected: the
  corpus is where the answer lives. A retrieved comma stating "X is forbidden" next to
  the question "Is X forbidden?" reveals the answer. Definitions state no rule, which
  is why the glossary (spec 0019) is safe grounding where the corpus is not.
- **Reusing the existing comma labeling as vocabulary grounding** — rejected: the judge
  sees `correct_answer` (`question_labeling_service.py:87-92`), entangling its labels
  with the answer.
- **A structured, API-visible glossary array** (`{term, meaning, official}` per entry,
  an earlier draft) — rejected once the two explanations merged into one message: a
  single flowing Italian paragraph, mirroring `ExplanationWriterAgent`'s own style, is
  simpler to combine, render and translate as one text. Term grounding is still
  internally ordinal-checked (FR-4) — only the *externally visible shape* changed from
  a structured list to prose plus a small hint list (FR-6). **Partially revisited
  2026-09-23 (FR-8, AD-9)**: `translation_hints` gained a `definition` field and the
  bot renders it as a separate block — narrower than what this bullet rejected, since
  `term_explanation`'s flowing paragraph is unchanged and stays the primary
  explanation; the glossary block is additive, not a replacement, and costs no new
  LLM output (`definition` is read straight from `glossary_entries`, spec 0019).
- **Pre-translating the vocabulary explanation into Russian directly** — rejected: the
  merged message (vocabulary + legal reasoning) is translated *as a whole*, once, by
  the existing translator (spec 0018), not generated twice per language.
- **Storing pre-translated hints on this feature's own response, computed live** —
  rejected: a hint is only as good as being reviewed once and reused everywhere; spec
  0019 already produces and stores `term_ru` for exactly this purpose. This feature
  reads it, never computes it.

## Functional Requirements

### FR-1: `GET /quiz-questions/{number}/explanation` gains two response fields

No new endpoint, no new query parameter. The existing response
(`QuizExplanationResponse`) gains:

```json
{
  "status": "explained",
  "explanation": "… (unchanged: the legal reasoning, spec 0017)",
  "citations": ["… (unchanged)"],
  "provenance": { "…": "unchanged" },
  "reason": null,
  "judge_rationale": null,
  "term_explanation": "La domanda chiede se… «carreggiata» indica…",
  "translation_hints": [
    {
      "term": "carreggiata",
      "definition": "Parte della strada destinata alla circolazione dei veicoli.",
      "term_ru": "проезжая часть"
    }
  ]
}
```

`term_explanation` is `null` when the second agent found nothing worth explaining, or
failed, or timed out (FR-5 — a degraded, not a failed, call). `translation_hints` is
`[]` whenever `term_explanation` is `null`, and otherwise carries the `(term,
definition, term_ru)` triple of every glossary entry `term_explanation` actually cites
(FR-4); terms the agent explains from its own knowledge, with no matching glossary
entry, appear in the prose but contribute no hint. `definition` is the glossary row's
own Italian text (spec 0019), not agent-generated (FR-8, AD-9) — it is now also
rendered as its own block by the bot, separate from `term_explanation`'s prose (FR-8),
in addition to feeding the translator's per-term pinning (FR-7, spec 0018 FR-8/AD-9).

`term_explanation` and its hints are populated **regardless of `status`**: even when
`status` is `insufficient_knowledge` (the corpus cannot justify the legal answer),
the candidate can still learn what the question's words mean — the two stages are
independent (AD-1).

### FR-2: Vocabulary grounding is answer-blind

Neither the vocabulary agent's request, its prompt, nor anything the service reads for
this stage carries `correct_answer`, `rule_explanation`, `core_concepts`, `topic`, or
any other field derived from the answer. It receives only the question `text`, the
image `description` (when present) and the glossary candidates (FR-4). The retrieval
query uses only the question's own stored embedding and text (FR-4). This is a design
choice for prompt focus and testability (AD-1) — by the time "Spiega" can be tapped the
user has already submitted and seen their own result, so it is no longer a privacy
requirement the way an earlier, pre-answer draft of this feature needed it to be.

### FR-3: The two stages run concurrently, under the existing deadline

`ExplanationService` gathers the vocabulary stage and the (unchanged) legal-explanation
stage with `asyncio.gather`, both under the single existing
`AppConfig.explanation_deadline_s` timeout (AD-1). Total added latency is therefore
`max(vocabulary, legal)`, not their sum. If the shared deadline fires, both stages are
cancelled and the call fails exactly as it does today (`ExplanationUnavailableError`,
`503`) — the deadline's meaning does not change, only what runs inside it.

### FR-4: Vocabulary candidates come from a hybrid retrieval over `glossary_entries`

`GlossaryReadRepository` returns up to `AppConfig.glossary_max_candidates` (default
`10`) entries as the union of two arms, deduplicated by id:

- **dense** — the `glossary_dense_k` (default `5`) entries nearest, by `<=>` over
  `embedding_3_small`, to the question's stored embedding of variant **`text`** in
  `quiz_question_embeddings` (the variant built from the question text alone, so no
  answer-derived field enters the query vector). No embedding call at runtime.
- **full-text** — the `glossary_text_k` (default `5`) entries whose `tsv_term` matches
  an OR of the question's Italian lexemes, ranked by `ts_rank`. The `italian`
  configuration stems both sides, so inflected uses of a term still match.

Entries found by both arms rank first, then by arm rank, with ties broken by id. A
question with no `text`-variant embedding row uses the full-text arm only and logs a
`warning`. An **empty result is valid and expected**, not an error: it is the normal
state while spec 0019's table is empty or has not yet been populated for a given term
(Independence from Spec 0019) — the vocabulary agent still runs, with no official
grounding to cite (FR-6).

### FR-5: A vocabulary-stage failure degrades, it does not fail the request

Unlike the legal-explanation stage (unchanged: its failure is `503`, FR-7 of spec
0017), an exception or an exhausted ordinal-retry (FR-6) in the vocabulary stage is
caught, logged at `warning`, and yields `term_explanation: null` — the response still
returns `200` with the legal explanation intact. The vocabulary stage is additive value,
not a load-bearing part of the existing contract.

### FR-6: Vocabulary grounding is ordinal-checked, via the agent's own output_validator

`QuestionExplainerAgent` returns:

- `explanation: str` — Italian, `min_length=1`, `max_length=900`. Explains what the
  question is asking and defines any term worth defining, in the same simple register
  as `ExplanationWriterAgent`'s own prompt. Every term it draws from a supplied
  candidate is quoted in guillemets on first use (`«carreggiata»`), mirroring the
  existing "Vero"/"Falso" quoting convention in `explanation_translator.ru.yaml` — both
  for readability and as the anchor `translation_hints` (FR-1) attaches to. A term the
  agent explains from its own knowledge, uncited, is written in plain prose with no
  guillemets and produces no hint.
- `cited_term_numbers: list[int] = []` — the ordinals of the supplied candidates it
  actually quoted, possibly empty (unlike the legal stage's `cited_comma_numbers`,
  which requires at least one — a question may need no official term at all).

`QuestionExplainerAgent` validates its own ordinals via a pydantic-ai `output_validator`
registered on the wrapped agent (mirroring `CommaLabelerAgent._validate_comma_numbers`,
spec 0014, AD-8): an out-of-range `cited_term_numbers` ordinal raises `ModelRetry`,
which pydantic-ai feeds back into the same conversation as corrective feedback before
the next attempt, up to `AgentConfig.num_retries` — the one retry budget for this and
any structural output issue, no separate service-level attempt counter.
`ExplanationService` no longer range-checks a citation itself: it only maps an
exhausted `UnexpectedModelBehavior` to the FR-5 degrade (`term_explanation: null`),
then resolves the cited ordinals of whatever valid response it did get back into their
glossary rows to build `translation_hints`.

`ExplanationWriterAgent` (spec 0012/0017) is migrated to the identical pattern as a
companion change (AD-8): both stages `ExplanationService` gathers concurrently (FR-3)
now validate their own citations the same way, so a reader of `ExplanationService`
finds no retry logic for either stage — only two `try/except` blocks mapping an agent
failure to its own outcome (FR-5's degrade for the vocabulary stage, FR-13's 503 for
the legal stage).

### FR-7: Bot rendering stays one edited-in-place message

`handle_explain_callback` renders `term_explanation` (when present), the existing
legal `explanation`/refusal line, and the glossary block (FR-8, when
`translation_hints` is non-empty) as sections of the **same** message — no new button,
no new keyboard row (AD-3). The combined text (all sections that were rendered) is
what gets stashed as `session.last_explanation` for a later "🇷🇺 Traduci" tap;
`translation_hints` is stashed alongside it (`session.last_explanation_hints`) and
forwarded, unchanged, to `POST /explanations/translate` (spec 0018, FR-8) on that tap
— the translator receives the glossary block as ordinary text within
`last_explanation` (it was already composed into the message the user saw) and uses
`translation_hints`' `term`/`term_ru` pair to keep the cited term itself pinned, the
same mechanism spec 0018 already applies to `term_explanation`'s prose; `definition`
is not part of what is forwarded to the translator, only of what the bot renders
locally (FR-8). Everything else about the "Spiega"/"Traduci" flow — the optimistic
edits, the staleness checks, the photo-caption overflow handling — is unchanged.

### FR-8: The glossary is a separate block, not woven into the prose

Each entry `term_explanation` cites (FR-6) is also shown as its own line, under a
short heading, **below** both paragraphs rather than only as an inline `«term»`
quotation inside the prose:

```
{term_explanation prose}

{legal explanation}

📖 carreggiata — Parte della strada destinata alla circolazione dei veicoli.
📖 banchina — Parte della strada, esterna alla carreggiata, destinata alla sosta o al transito dei pedoni.
```

The prose (FR-6) is unchanged — it still explains the question in context and still
quotes cited terms in guillemets on first use — this block is additive, a scannable
recap for a candidate who wants the definition without re-reading the paragraph, not a
replacement for it. Built entirely from `translation_hints` (FR-1): one line per hint,
`term` and `definition` exactly as `glossary_entries` (spec 0019) stores them, in the
same order `cited_term_numbers` (FR-6) lists them. No block is rendered when
`translation_hints` is empty (`term_explanation: null`, or a prose with no cited
term).

QUI forse ha senso rivedere un po' il data model di storage, se salvare nella cache non solo l'ultima ma tutte legate all'id del messaggio
in un dizionario e salvare
```python
class TermExplanation(BaseModel):
    term: str
    term_ru: str
    definition: str

class QuestionExplanation(BaseModel):
    text: str # Generato da LLM
    terms: list[TermExplanation]
    
class QuizExplanation(BaseModel): 
    question_explanation: QuestionExplanation
    answer_explattion: str # Generato da LLM

bot_cache_state: dict[int, QuizExplanation] = {}

state[1] = {
    "question_explanation": {
        "text": "...", 
        "terms": [{"term": "...", "term_ru": "...", "explanation": "..."}, ...]
    },
    "answer_explanation": "..."
}

```

## Non-Goals

- No new endpoint, no new bot button, no new keyboard row (AD-3).
- No target language other than Russian; no language picker.
- No caching of the vocabulary explanation (AD-2): both stages are generated live,
  symmetrically.
- No change to `POST /{number}/label`, `POST /{number}/check`, or the labeling/judge
  machinery — the vocabulary stage never touches them.
- No image-aware (multimodal) vocabulary explanation: the agent reads the stored image
  *description*, not the image.
- No requirement that spec 0019 be implemented first, or at all, for this feature to
  ship (Independence from Spec 0019).
- No requirement that spec 0018's hints amendment (FR-8/AD-9 there) be deployed first:
  without it, `POST /explanations/translate` simply ignores an unrecognized field or
  (once deployed) receives an empty `hints` list with unchanged behavior.

## Architectural Decisions

### AD-1: Two independent agents, gathered concurrently, one merged response

`QuestionExplainerAgent` (`agents/question_explainer/`, `@agent`, mirroring
`ExplanationWriterAgent`'s wiring exactly: `AgentConfigRepository`,
`OpenRouterProviderComponent`, `LlmCallTrackerProvider`, zero-arg `__init__`) with
`configs/agents/question_explainer.yaml` — Italian output, and therefore **unsuffixed**
per `.claude/rules/agent-config-naming.md` (it is not itself a Russian-targeting agent;
Russian is produced afterward, on the whole merged text, by the existing translator).
Both it and the new `GlossaryReadRepository` (`@repository`, `guidami_ai_patente/
repositories/`, FR-4) are wired the pywire way, like every other collaborator in this
package (`.claude/rules/pywire-di.md`): `ExplanationService` — itself already a
`@service` with `Autowired[T]` fields, unchanged in shape — gains two more,
`vocabulary_agent: Autowired[QuestionExplainerAgent]` and `glossary:
Autowired[GlossaryReadRepository]`. No constructor, no manual resolution; both are
declared and populated exactly like its existing `writer`/`reader`/`questions` fields.
`ExplanationService` gathers the new agent alongside the unchanged legal-explanation
path; because `term_explanation` needs neither `correct_answer` nor the labeling/judge
machinery, it runs whether the legal path succeeds, refuses (`insufficient_knowledge`),
or is never
reached for other reasons — the two stages' outcomes are reported independently in one
response (FR-1).

### AD-2: Both stages generated live; no new cache table

The legal-explanation stage has never been cached (it varies by `submitted` and is
regenerated on every call, an accepted cost, spec 0017). Caching only the vocabulary
stage — as this spec's first draft proposed, with its own table and a
`content_hash` invalidation scheme — would be an asymmetric complication introduced
for one half of a now-unified feature. Retrieval (FR-4) already keeps its cost bounded
(~1-1.5k prompt tokens against ~250 glossary entries, versus 6-16k for whole
definition articles), which was the cache's original justification; with that
justification gone, symmetry with the existing stage wins.

### AD-3: No bot-side change beyond the existing "Spiega" handler

The button already exists only in the post-answer keyboard
(`_answer_result_keyboard`, spec 0017); this feature adds no keyboard state, so the
three-keyboard-builder consolidation an earlier draft planned (to add a fourth button
copy) is no longer needed. `handle_explain_callback` changes only in what it renders
and what it stashes on the session (FR-7); `_explanation_result_keyboard`,
`handle_translate_callback` and `QuizApiClient.translate_explanation` change only to
also carry `translation_hints` through, unchanged in every other respect.

### AD-4: Answer-blindness is structural, not a prompt instruction

`QuizQuestionRepository.find_question_context` returns `correct_answer` alongside
`text` and `description` (`quiz_question_repository.py:135-160`). Reusing it would put
the answer in reach of the vocabulary stage. A **new** read method and model select
only `quiz_id`, `text`, the joined image `description`, and the question's own
`text`-variant embedding (for FR-4's dense arm); the vocabulary agent's request DTO has
no answer-derived field, and a test asserts it (Testing). The retrieval query vector is
the question's `text`-variant embedding for the same reason: the other variants embed
`topic`, `search_queries` or descriptions (`quiz_variant_registry.py:30-61`).

### AD-5: Hybrid retrieval over a precomputed glossary, not long-context grounding

With ≈ 250 entries, retrieving ~10 candidates costs ~1-1.5k prompt tokens instead of
6-16k for whole definition articles. Both arms are needed: the full-text arm alone
misses concepts phrased differently, the dense arm alone misses an exact term buried
in a long question. The union mirrors `CandidateSetService`'s two-arm shape
(`labeling/services/candidate_set_service.py`), without its judge stage: here the agent
selects, and a wrong extra candidate costs a few tokens, not a wrong label. The table
has no vector index (spec 0019, Non-Goals), so the dense arm is an exact scan — fine at
~250 rows.

### AD-6: Response DTO language follows the existing convention

`QuestionExplainerResponse` docstring and `Field(description=...)` are Italian
(prompt-facing schema, shipped to the LLM); the request DTO stays English. A
`logger.warning` on degrade (FR-5) stays English.

### AD-7: Reuse `ExplanationUnavailableError` — only for the legal stage

The legal stage's failure/timeout semantics are unchanged (spec 0017, FR-13): still
`ExplanationUnavailableError`, still `503`. The vocabulary stage never raises it — its
failure is swallowed per FR-5. No new exception class.

### AD-8: Both agents self-correct via `output_validator`, not a service-level retry loop

Ordinal-range grounding (FR-6) is enforced by each agent itself, not by
`ExplanationService`. This departs from `ExplanationWriterAgent`'s original spec 0012
design (`_call_writer`'s manual retry loop, keyed off a service-level
`_CITATION_ATTEMPTS` constant) in favor of the pattern `CommaLabelerAgent` already uses
(spec 0014): an `output_validator` raising `ModelRetry` when `ctx.deps` shows an
ordinal outside the supplied set.

Chosen over keeping `_call_writer`'s loop for two reasons: `ModelRetry` gives the model
targeted, in-conversation feedback ("ordinals X are invalid, choose within 1-N") before
its next attempt, instead of a blind independent `agent.run()` call with no memory of
what it got wrong; and it removes duplicated range-check logic from the service (today
`1 <= ordinal <= supplied` is recomputed by hand in `_call_writer`) in favor of a single
place, next to the prompt that produced the ordinal, exactly where `ctx.deps` already
carries the count needed to check it.

This is a **decision that also reaches back into already-shipped spec 0017 code**:
`ExplanationWriterAgent`/`ExplanationService._call_writer` are migrated to the same
pattern as a companion change to this spec's implementation, not a spec of their own —
the two agents `ExplanationService` gathers (FR-3) would otherwise validate
identically-shaped citations two different, mutually invisible ways. The migration
removes `_CITATION_ATTEMPTS`/the retry loop from `_call_writer`, which becomes a single
`try/except` around one `agent.run()` call; `AppConfig.explanation_deadline_s`'s
existing default already assumed the *combined* cost of what is now the agent's own
retries, so no config change follows from this alone.

### AD-9: The glossary block costs no new LLM call, and translates for free

`definition` (FR-8) is read straight from the `glossary_entries` row (spec 0019,
FR-7 there) that `ExplanationService` already resolves each `cited_term_numbers`
ordinal against to build `translation_hints` (FR-6) — no new agent output field, no
new retrieval, no new prompt. `QuestionExplainerAgent`'s own response is unchanged by
FR-8: it still only returns `explanation` and `cited_term_numbers`.

Translation is equally free: spec 0019 (Rejected shapes) deliberately does not store a
pre-translated Russian definition, precisely because "the whole message is translated
once, on demand" by `ExplanationTranslatorAgent` (spec 0018) — a decision this spec's
glossary block relies on rather than revisits. Once the block is composed into the
message text the user sees (FR-7), a "Traduci" tap translates it exactly like the rest
of the message: the *term* stays pinned via `translation_hints`' `term_ru` (the
existing spec 0018 FR-8/AD-9 mechanism, unchanged), while its *definition* is
translated freely by the same LLM call already translating
`term_explanation`/`explanation` — never a separately stored or separately requested
Russian definition.

## Independence from Spec 0019

The vocabulary stage's retrieval (FR-4) is written to tolerate an empty
`glossary_entries` table from day one (an empty result is an explicitly valid case).
It cannot tolerate a **missing** table (relation does not exist), so whichever spec's
implementation plan lands first is responsible for creating the table (empty) in
`db/init.sql` — spec 0019's Data Model section is the authoritative schema either way
(see that spec's own "Independence from Spec 0020" section). If this spec's plan is
implemented first, its first task stages that `CREATE TABLE` (and nothing else from
spec 0019 — no agent, no population); if spec 0019 lands first, this spec's plan finds
the table already present and does not redefine it.

## Data Model

No new table owned by this spec. `AppConfig` gains: `glossary_dense_k`,
`glossary_text_k`, `glossary_max_candidates` (retrieval depths, FR-4) — deployment
configuration, never judge identity, same status as `explanation_deadline_s`. No change
to `explanation_deadline_s` itself (FR-3: concurrent, not additive).

`QuizExplanationResponse` (API): + `term_explanation: str | None`, +
`translation_hints: list[TranslationHintResponse]` (`{term: str, definition: str,
term_ru: str}` — `definition` added by FR-8, sourced verbatim from the `glossary_entries`
row (spec 0019) `ExplanationService` already resolves each cited ordinal against, no
new read).
`Explanation` (domain model, `guidami_ai_patente/models/explanation.py`): +
`term_explanation: str | None = None`, + `translation_hints: tuple[TranslationHint,
...] = ()` — both fields sit outside the existing `_require_a_coherent_shape`
validator (AD-1: populated independently of `result`).

Bot: `QuizExplanation` (`guidami_ai_patente_bot/models/quiz_explanation.py`) gains the
same two fields; `QuizSession` gains `last_explanation_hints:
tuple[TranslationHint, ...] = ()` alongside the existing `last_explanation`.

## Constraints

- pywire field injection for the new agent and the glossary read repository
  (`.claude/rules/pywire-di.md`).
- Router body (`quiz_questions.py`) stays a thin controller: this spec adds no new
  route, only new fields on the existing response, produced entirely inside
  `ExplanationService`.
- One class per file; enums (if any) in `enums/`; no `continue` in loops; lazy `%s`
  logging with levels used purposefully.
- Agent YAML resolved through the existing `AppConfig.agents_dir`; no new config root.
- SQL through `psycopg.sql` identifiers taken from config; vector parameters cast with
  `%s::vector` where a literal vector is bound (`code-conventions.md`).
- Tests live in `tests/` mirroring `src/`, no `__init__.py`, pytest, TDD.

## Testing

- **Ordinal validation** (unit, agent-level): an out-of-range `cited_term_numbers`
  ordinal self-corrects via `QuestionExplainerAgent`'s own `output_validator`
  (`test_an_out_of_range_ordinal_self_corrects_on_retry`, mirroring
  `test_comma_labeler_agent.py`); once `AgentConfig.num_retries` is exhausted the agent
  raises `UnexpectedModelBehavior`
  (`test_an_ordinal_that_never_self_corrects_raises_unexpected_model_behavior`). A
  repeated ordinal is rejected by the response model itself
  (`test_question_explainer_response_rejects_repeated_ordinal`).
- **Degrade on exhaustion** (unit, service-level, fakes): `ExplanationService` maps an
  `UnexpectedModelBehavior` raised by the vocabulary agent to `term_explanation: None`
  (FR-5), it does not propagate it
  (`test_vocabulary_stage_degrades_on_exhausted_retries`).
- **`ExplanationWriterAgent` migration** (unit, agent-level, AD-8): the same two tests
  mirrored for the legal stage (self-correction, exhausted-retry), replacing the two
  service-level retry tests this migration retires
  (`test_an_out_of_range_citation_is_retried_then_becomes_a_503`,
  `test_a_retry_that_cites_correctly_is_accepted`).
- **Answer-blindness** (unit): the vocabulary request DTO and the new context/read model
  expose no `correct_answer`/`rule_explanation`/`core_concepts`/`topic` field
  (`test_question_explainer_request_has_no_answer_field`).
- **Concurrency** (unit, fakes): both stages are awaited via `gather`; a vocabulary
  failure does not cancel or affect the legal stage's result, and vice versa; a shared
  deadline expiry fails the whole call as today.
- **Independent of `status`**: `term_explanation` is populated on an
  `insufficient_knowledge` legal outcome, not only on `explained`
  (`test_term_explanation_present_when_legal_explanation_is_insufficient`).
- **Glossary retrieval** (`@pytest.mark.integration`): the full-text arm finds an
  inflected form (`carreggiate` → `CARREGGIATA`); the dense arm returns a
  semantically-near entry; an entry found by both ranks first; a question with no
  `text` embedding degrades to the full-text arm; an **empty table** returns `[]`
  without error (Independence from Spec 0019).
- **Endpoint** (`api_client` with a fake vocabulary agent): response shape carries
  `term_explanation`/`translation_hints`; a vocabulary-agent exception still returns
  `200` with `term_explanation: null` and the legal explanation intact.
- **Bot**: the rendered message concatenates both paragraphs; `last_explanation` and
  `last_explanation_hints` are both stashed after a successful "Spiega"; a later
  "Traduci" tap forwards the stashed hints unchanged; no new keyboard row appears
  anywhere.
- **Glossary block** (FR-8, unit): the rendered message includes one line per
  `translation_hints` entry, in `cited_term_numbers` order, using `term`/`definition`
  verbatim; no block appears when `translation_hints` is empty
  (`test_glossary_block_omitted_when_no_terms_cited`). `definition` in the API response
  matches the `glossary_entries` row's own text, not agent output
  (`test_translation_hint_definition_is_read_from_the_glossary_row`).

## Feasibility Evidence

Verified 2026-09-21/22 on branch `feat/backend`.

- **AD-1 / FR-3** — `services/explanation_service.py:72-127` (`execute`/`_explain`,
  the existing `asyncio.timeout(explanation_deadline_s)` wrapper and the
  select-then-write sequencing this spec parallelizes); `agents/explanation_writer/dto/
  explanation_writer_response.py:19-46` (`explanation`, `cited_comma_numbers`, the
  `_reject_repeated_ordinals` validator this spec's `QuestionExplainerResponse`
  mirrors).
- **AD-8** — `labeling/agents/comma_labeler/comma_labeler_agent.py:30-57`
  (`_validate_comma_numbers`/`output_validator`/`ModelRetry`, the pattern FR-6 mirrors
  for both agents); `tests/labeling/agents/comma_labeler/test_comma_labeler_agent.py`
  (`test_an_out_of_range_ordinal_self_corrects_on_retry`, the test shape to mirror for
  `QuestionExplainerAgent` and the migrated `ExplanationWriterAgent`).
- **FR-8 / AD-9** — `docs/superpowers/specs/2026-09-21-definition-glossary-design.md`
  FR-7 and its `CREATE TABLE glossary_entries` (Data Model there): the table already
  carries the Italian `definition` alongside `term`, so FR-8 reads an existing column,
  not agent output; that same spec's Rejected shapes entry "Storing a full Russian
  translation (definition, summary) per glossary entry" is the prior decision AD-9
  relies on (the whole merged message, glossary block included, is translated once by
  `ExplanationTranslatorAgent`, spec 0018 — never a stored Russian definition).
- **AD-4** — `repositories/quiz_question_repository.py:135-160` selects
  `q.correct_answer`; `labeling/services/question_labeling_service.py:87-92` passes
  `correct_answer` to the judge; `ingestor/services/quiz/quiz_variant_registry.py:30-61`:
  variant `text` embeds `text` only, the others add `topic`, `search_queries` or
  `image_description`; `configs/ingestor_config.yaml:57` indexes `text` among the
  variants.
- **AD-5** — `db/init.sql:74-86` (`quiz_question_embeddings`,
  `embedding_3_small VECTOR(1536)`); `labeling/services/candidate_set_service.py:32-50`
  (the two-arm union pattern); `commons/repositories/db/corpus_read_repository.py`
  (`dense_top_k`, `text_match_top_k`, `extract_lexemes` — the query shapes to mirror).
- **AD-7 / FR-5** — `guidami_ai_patente/exceptions/` (`ExplanationUnavailableError`
  already mapped to `503`, `exception_handlers.py`).
- **FR-1 / Data Model** — `models/explanation.py:11-43` (`Explanation`'s
  `_require_a_coherent_shape` validator — confirmed the new fields sit outside its
  `result`-based branches); `api/schemas/quiz_explanation.py:38-56`
  (`QuizExplanationResponse`); `mappers/explanation_mapper.py:11-37`
  (`ExplanationMapper.from_explanation_to_response` — the mapping this spec extends).
- **FR-7 / AD-3** — `bot/handlers/quiz_handlers.py:69-84,208-335`
  (`_explanation_result_keyboard`, `handle_explain_callback`,
  `handle_translate_callback` — confirmed the button already lives only in the
  post-answer keyboard, so no consolidation is needed); `bot/models/quiz_session.py`
  (`last_explanation`, the field this spec adds a sibling to); `bot/models/
  quiz_explanation.py` (`QuizExplanation`, deliberately narrower than the API
  response — this spec adds the two new fields here too).
- **Independence from Spec 0019** — `docs/superpowers/specs/
  2026-09-21-definition-glossary-design.md`, "Independence from Spec 0020" section
  (mirror of this section, written together).
- **Enhanced by spec 0018** — `docs/superpowers/specs/
  2026-09-18-explanation-translator-design.md` FR-8/AD-9 (the 2026-09-22 amendment
  this spec's `translation_hints` field is produced to feed).

## Open Questions

- [ ] **non-blocking** — Exact prompt text for `QuestionExplainerAgent` (register,
  how much of the question to restate vs. assume understood, handling of a question
  whose image has no stored description) — left to implementation.
- [ ] **non-blocking** — `max_tokens` and model for `QuestionExplainerAgent` (proposed:
  same `openrouter/google/gemini-2.5-flash` as its siblings) — tune with real output.
- [ ] **non-blocking** — Retrieval depths `glossary_dense_k`/`glossary_text_k`/
  `glossary_max_candidates` (proposed 5/5/10): tune on real questions once spec 0019's
  table has data; before that, every question exercises the "empty result" path
  (FR-4), which is exactly what needs to keep working regardless.
- [ ] **non-blocking** — Whether a real-LLM integration test is added for the new
  agent, following the sibling agents' precedent, if any — left to implementation to
  confirm.
- [ ] **non-blocking** — Message-length margin once real output lengths are known:
  `term_explanation` (`max_length=900`) plus the existing legal explanation (itself
  unbounded today but consistently short in practice) plus the FR-8 glossary block
  (one line per cited term, unbounded by count today) should stay well inside
  Telegram's 4096-character limit; the plan should confirm with a rendering test rather
  than recomputing worst-case arithmetic here.
- [ ] **non-blocking** — Exact glossary-block heading/formatting (the `📖` marker and
  layout above are illustrative) and whether `glossary_max_candidates`/`cited_term_numbers`
  need their own cap on *rendered* lines, separate from the retrieval-candidate cap
  (FR-4) — left to implementation.

## Follow-ups after implementation

- Run `second-brain:update` (`architecture.md`, `patterns.md`, `testing.md`) and record
  an ADR (`second-brain:adr`) for: merging two independently-gathered LLM stages into
  one existing endpoint response instead of a second endpoint, and hybrid retrieval
  over a precomputed glossary as answer-blind grounding.
- Update the `CLAUDE.md` API endpoints table's description of `GET
  /{number}/explanation`.

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by the assistant on 2026-09-21/22, based on the
  Feasibility Evidence above (source reads and a dispatched read-only research
  subagent, not a dedicated feasibility-compiling skill)

## Changelog

- **2026-09-23 (later)** — FR-8/AD-9: the glossary is now also rendered as its own
  block, separate from `term_explanation`'s prose, not only as inline `«term»`
  guillemets — partially revisiting the "structured, API-visible glossary array"
  rejection (Shapes considered and rejected). `translation_hints` gains a `definition`
  field, read verbatim from the `glossary_entries` row already resolved for FR-6 (no
  new agent output, no new retrieval); on "Traduci", the block translates for free as
  part of the whole merged message (spec 0018), with only the term itself pinned via
  the existing `term_ru` hint — no stored Russian definition, consistent with spec
  0019's own Rejected shapes.
- **2026-09-23** — FR-6/AD-8: `QuestionExplainerAgent`'s ordinal-grounding moves from a
  service-level retry loop (`ExplanationService`, mirroring `_call_writer`'s original
  spec 0012 shape) to a pydantic-ai `output_validator` on the agent itself, mirroring
  `CommaLabelerAgent` (spec 0014) — chosen for targeted in-conversation retry feedback
  over a blind independent retry, and to keep the range check next to the prompt that
  produced the ordinal. `ExplanationWriterAgent` (spec 0012/0017) is migrated to the
  same pattern as a companion change, so both stages `ExplanationService` gathers
  (FR-3) validate citations identically; `_CITATION_ATTEMPTS` and `_call_writer`'s
  retry loop are retired.
- **2026-09-22 (later)** — Full redesign after discussing the shape with the actual
  end user: merged into the *existing* `GET /explanation` (spec 0017) instead of a new
  endpoint/button; two agents now run concurrently via `asyncio.gather` under the
  existing deadline; the vocabulary stage degrades on failure instead of raising;
  dropped the dedicated cache table (both stages now generated live, symmetrically);
  dropped the structured `{term, meaning, official}` glossary array in favor of prose
  plus a small `translation_hints` list, consumed by spec 0018's new `hints` field;
  `QuestionExplainerAgent`'s config is unsuffixed (Italian output — Russian happens
  afterward, on the whole merged text). Renumbered from 0019 to 0020 (0019 is now the
  glossary spec alone).
- **2026-09-21** — Renumbered 0019 → 0020 and reshaped: grounding widened from CdS
  art. 3 alone to a hybrid retrieval over a precomputed glossary (spec 0019), after
  measuring that art. 3 alone leaves whole term families unanchored (road classes,
  lights, arresto/fermata/sosta, all RCA vocabulary). Agent configs targeting one
  language carry it in the file name (rule added: `.claude/rules/agent-config-naming.md`).
- **2026-09-21** — Initial draft (as 0019), from an interactive
  `superpowers:brainstorming` session and a `mattpocock-skills:grilling` round (output
  form, lazy cache, button placement, RAG scope, content-hash invalidation, FK with
  cascade, single `GET`, `official` flag) — superseded by the 2026-09-22 redesign
  above.
