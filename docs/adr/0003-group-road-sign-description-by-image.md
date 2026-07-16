# ADR 0003: Group Road Sign Description By Image, Not By Quiz

## Status

Accepted

## Context

`ImageDescriptionEnricher` used to dedup quiz sub-questions on the triple
`(image, topic, text)` before calling `RoadSignDescriberAgent`. The same
image referenced by different quiz texts triggered multiple divergent
vision-LLM calls: wasted cost, and an inconsistent `image_description`
for the same physical road sign depending on which quiz asked about it.

`RoadSignDescriberAgent` is already answer-blind
(`adr/0001-road-sign-describer-answer-blind.md`) and its system prompt
already tells the model to treat the quiz text as weak, possibly-false
context. Given that, per-quiz specialization of the description was
never earning its extra cost — the describer wasn't meant to use the
quiz text as anything more than a hint.

## Decision

Group by the image filename only. `ImageDescriptionEnricher` now issues
exactly one vision call per distinct image, concatenating the contexts of
every quiz that references it (`RoadSignDescriberRequest.contexts:
list[QuizContextModel]`, one entry per distinct topic among those quizzes)
into a single request. The resulting `image_description` and
`image_analysis` (full LLM output: `visual_analysis`, `name`,
`description`) are broadcast to every quiz sharing that image.

Per-image calls run concurrently (`asyncio.gather` under an
`asyncio.Semaphore(max_concurrency)`, `IngestorConfig
.road_sign_describer_concurrency`, default `8`) so batching by image
doesn't serialize a large quiz bank behind hundreds of sequential calls.

## Alternatives considered

- **Keep the `(image, topic, text)` triple key, but cache/reuse when text
  is textually identical**: doesn't address the actual problem —
  different quizzes about the same sign rarely share exact text, so this
  would still fire one call per quiz in practice.
- **Pass `correct_answer` or richer per-quiz signals to specialize the
  description per quiz**: rejected for the same reason as
  `adr/0001-road-sign-describer-answer-blind.md` — the describer isn't
  meant to reason about which statement is true, and specializing on
  quiz text reintroduces the exact inconsistency this decision removes.

## Consequences

- One `llm_call_logs` row per image instead of per triple — fewer, cheaper
  vision calls for images referenced by many quizzes.
- `image_description` is now identical across every quiz sharing an
  image — the intended trade-off, not a side effect to guard against.
- `NormReferenceEnricher` now receives the same, per-image
  `image_description` as context for every quiz sharing that image,
  instead of a per-quiz-text one. This is a knowingly coarser context,
  accepted for the consistency/cost win.
- Concurrency introduces `asyncio.run`/`asyncio.gather` inside
  `ImageDescriptionEnricher.execute`, which stays a sync method (the
  ingestion CLI has no running event loop). If enrichment is ever driven
  from inside an already-running loop, `asyncio.run` will raise
  `RuntimeError` — at that point `execute` would need to become async,
  which is out of scope today.
