# LLM model migration — larger/newer models on the Gemini free tier (draft)

Date: 2026-09-29
Status: **Draft, parked** — captured to keep track of the discussion. Not approved, not
checked against `clean-architecture`, not handed to `writing-plans`. Work stops here for now.

## Why parked

The cross-provider model-name problem (see "Deferred: model names across providers") was judged
too complicated to solve at this point. Everything below is the state of the brainstorming
when it was parked.

## Goal

Move the LLM agents to larger and/or newer models to improve output quality, while keeping
the cost at zero by using the Google Gemini API free tier (Google AI Studio) during
development and batch runs.

## Preconditions

- `2026-09-25-llm-provider-decoupling-design.md` (Phase 1, the `LlmModelProvider` seam) shipped.
  At the time of writing it is still a draft and nothing exists under `src/commons/ai/llm_providers/`.
- `2026-09-25-llm-provider-decoupling-phase2-draft.md` (Gemini adapter, `expects_cost=False`)
  shipped. This spec adds no infrastructure code of its own.
- The free tier is reachable only through the native Gemini API, not through OpenRouter.

## Decisions taken during brainstorming

- **Placement:** this is a separate spec about *what* to migrate. Provider infrastructure stays in the
  Phase 1/2 specs.
- **Provider scope:** the provider stays **global per deployment**, as in Phase 1. It is switched
  manually when the live API phase needs it. No per-agent provider, no automatic fallback.
- **Tiering by impact:**
  - Tier A, most capable free model: `road_sign_describer`, `comma_labeler`,
    `explanation_writer`, `explanation_translator.ru`.
  - Tier B, latest Flash/Flash-Lite: `norm_reference_describer`, `retrieval_judge` (evaluation only),
    `glossary_extractor`, `glossary_term_translator.ru`, `glossary_definition_simplifier`,
    `glossary_enricher`, `question_explainer`.
  - Concrete model ids are **not** fixed here: free-tier models change, so they are read from the
    AI Studio model list at adoption time.
- **Quota handling:** a daily-quota error (HTTP 429) fails the run explicitly and must not be retried
  by `num_retries`. No new resume machinery: rely on the per-element idempotency the quiz enrichment
  already has (`FilterAlreadyDoneStep`), rerun the next day. RPM pressure is handled by lowering
  `--concurrency`. If clean stop + resume turned out to be complicated, failing is acceptable.
- **Quality gate:** none formal — visual inspection of a sample. Mitigation: rolling back means restoring
  the previous `model_name`; the previous configuration epoch's labelings stay valid.

## Facts to verify before this can move on

- Free-tier RPM/TPM/RPD are **not published** in the docs; they live in the AI Studio rate-limit
  dashboard and are "not guaranteed". Read them there. The pricing page summary used during
  brainstorming was inconsistent, so re-check which models are actually free.
- Free-tier content may be used by Google to improve its products. Acceptable here (public legal
  text and quiz bank, no personal data), but confirm nothing user-submitted reaches the batch agents.
- Whether `label-golden-set` is idempotent across reruns (not verified; quiz enrichment is).
- Correction to an earlier assumption: `retrieval_judge` is evaluation-only; the live "judge" is
  `comma_labeler`, so that is the model whose quality matters for the live path.

## Rollout and epoch notes

- Suggested order, one commit each: describer, labeler, writer/translator, the rest.
- Changing `comma_labeler`'s model creates a new configuration epoch (`judge_model` is part of it). Nothing is
  relabeled automatically: labelings are recomputed lazily on each cache miss, or in bulk with
  `uv run label-golden-set`.
- Changing the describer's model affects `image_description`, hence the 7099 files in `data/enriched/`
  and the quiz embeddings. Spec 0023 (answer-aware image description regeneration) touches the same
  data: coordinate with it so the descriptions are regenerated once, not twice.

## Deferred: model names across providers

OpenRouter ids (`google/gemini-2.5-flash`) differ from native Gemini ids (`gemini-2.5-flash`), so switching
the global provider means every agent's `model_name` changes (Phase 1, Section 9 caveat). Options
considered:

1. A `configs/models.<provider>.yaml` overlay mapping agent name to `model_name`, applied when the agent
   config is loaded. Prompts stay single-sourced; switching provider is one config value.
2. Keep `model_name` in each YAML and edit the files by hand at every provider switch.

Neither was chosen. Decision deferred; until then the migration to Gemini would be a manual edit of the
agent YAMLs (option 2).

## Non-goals

Per-agent provider selection, automatic provider fallback, a formal evaluation harness, and any of
the provider infrastructure code owned by the Phase 1/2 specs.

## Still to do if resumed

- Resolve the model-name mapping question above.
- Run the `clean-architecture` check required by `.claude/rules/clean-architecture-review.md`.
- Grill the remaining open points, then present the design for approval and hand off to `writing-plans`.
