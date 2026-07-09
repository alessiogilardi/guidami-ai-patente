# ADR 0001: Road Sign Describer Stays Answer-Blind

## Status

Accepted

## Context

`RoadSignDescriberAgent` (vision LLM agent, part of the quiz enrichment
pipeline) produces a `visual_analysis` / `name` / `description` triple
from an image plus `topic`/`text`. It does not know whether the quiz
statement in `text` is true or false — `RoadSignDescriberRequest` never
receives `correct_answer`. The second-stage agent
(`NormReferenceDescriberAgent`) already receives `correct_answer` and is
responsible for rule verification and RAG metadata generation.

The describer's prompt includes an explicit objectivity guard: quiz text
can be deliberately false, so the model must describe only what the
image shows, not what the text claims.

A trade-off was raised during design: would passing `correct_answer`
into the describer's input let it produce a more targeted
`visual_analysis`/`description` — focused specifically on the detail
that confirms or refutes the statement — improving downstream
usefulness?

## Decision

Keep `RoadSignDescriberAgent` answer-blind. `correct_answer` is not
added to `RoadSignDescriberRequest`.

## Alternatives considered

- **Pass `correct_answer` into the describer's request**: would let the
  model target the specific visual detail that confirms/refutes the
  statement. Rejected: judging true/false is not "describing an image"
  — that responsibility belongs to the rule-verification stage
  (`NormReferenceDescriberAgent`, or a future LLM-as-judge component),
  which already has `correct_answer`. It also risks motivated
  reasoning — a model told the statement is false may hallucinate a
  corroborating visual detail instead of describing the image
  objectively, reintroducing under a different name the exact bias the
  prompt's objectivity guard is meant to prevent.

## Consequences

- `RoadSignDescriberRequest` stays `{topic, text}`;
  `RoadSignDescriberMapper.from_enriched_quiz_to_request` is unaffected.
- No evidence yet that the answer-blind design underperforms in
  practice.
- If real-world output quality turns out insufficient (vague
  descriptions, missing the decisive detail), revisit this decision:
  add `correct_answer: bool` to the request DTO, wire it through the
  mapper, and add an explicit anti-confirmation instruction to the
  prompt to mitigate the bias risk. Treat that as a new decision
  superseding this one, not a silent prompt tweak.
