# ADR 0013: The Retrieval-Quality LLM Judge Is Its Own Top-Level Package

## Status

Proposed

## Context

Spec 0007's retrieval evaluation harness (`ingest evaluate retrieval`) measures
retrieval quality with deterministic, judge-free signals only. Its Non-Goals
section explicitly excludes "LLM-as-judge relevance scoring": deterministic
signals cost nothing and run in CI, and an untargeted judge run over the whole
corpus would be wasteful before the judge-free signals identify which
subpopulation to target. FR-9 of that spec exports exactly that subpopulation
(the questions its deterministic signals cannot decide) for a future judge to
consume — but deliberately stops at data, with no `RelevanceJudge` protocol, no
provider abstraction, no prompt.

The user asked for that judge now: an agent that reads a quiz (text + answer)
and its top-10 most similar commas from dense retrieval, and answers whether
those commas clearly and unambiguously explain why the answer is true or
false — plus a service that samples random quiz questions and calls the agent
per question, and a script to run it. The explicit ask was for the shortest
path: an agent, a service, a script, nothing more.

Two placement questions had to be resolved before writing any code:

1. Does this measurement live inside `ingest evaluate retrieval` (as a new
   mode of the existing harness), or as its own thing?
2. Does building it now mean spec 0007's Non-Goal should be edited to match?

On (2): the user explicitly decided **not** to amend spec 0007. Its Non-Goals
section still reads as excluding an LLM judge, and this decision records why
that is not a contradiction: spec 0007 excludes the judge from *itself* — from
its own manifest-driven, CI-run harness — not from the codebase. This module is
the judge that Non-Goal deferred, arriving as a separate, deliberately
lighter-weight tool instead of as an amendment to the harness the Non-Goal was
written to keep judge-free.

On (1): the ingest CLI's `prepare`/`index`/`reset`/`status`/`evaluate` commands
all share `RunArtifactWriter`-based run artifacts (`manifest.json`/`report.md`/
`run.log`), a `--dry-run`/`--plain` flag surface, and a command-specific
manifest type that `logging_setup._build_manifest` requires on pain of raising.
That machinery exists because those commands are meant to run unattended in a
pipeline and be auditable after the fact. This judge is neither: it is an
exploratory measurement, re-run by hand a few times to gauge whether the LLM
judge itself is stable, then once more with a larger sample for an estimate —
closer in spirit to `test_data_sampler/sampler.py`'s one-shot script than to
`ingest evaluate retrieval`'s run-artifact-producing harness.

**Amendment (2026-08-21, spec 0011 phase 2):** this Context described the
module as a whole when it held one script. It now holds two:
`evaluate-retrieval-judge` (this ADR's original subject, unchanged, still
writes nothing but an optional `results.json`) and a second entry point,
`label-golden-set`, which persists a labeled golden set to Postgres
(`labeling_runs`/`quiz_labelings`/`quiz_comma_labels` — see `database.md`).
The reasoning above no longer describes the module's relationship to
persistence in general — see the Decision and Consequences sections below for
what changed and what did not.

## Decision

`src/retrieval_evaluation/` is a new top-level package, a sibling of
`parsers/`/`scrapers/`/`test_data_sampler/`, not a mode of `ingest evaluate
retrieval` and not a package under `guidami_ai_patente_ingestor/cli/`:

- `agents/retrieval_judge/retrieval_judge_agent.py` — `RetrievalJudgeAgent(BaseAgent[
  RetrievalJudgeRequest, RetrievalJudgeResponse])`, the same pattern as
  `RoadSignDescriberAgent`/`NormReferenceDescriberAgent`. `agents/` is a generic
  per-role container (parallel to `services/`/`models/`), holding one named
  subpackage per agent; today just `retrieval_judge/`. Its sibling
  `agents/retrieval_judge/dto/` holds its request (English) and response
  (Italian, prompt-facing) DTOs.
- `services/retrieval_judge_evaluation_service.py` —
  `RetrievalJudgeEvaluationService`: samples `n` random quiz rows via the
  existing `QuizReadRepository.fetch_with_vectors`, retrieves each question's
  top-`k` commas via the existing `CorpusReadRepository.dense_top_k` (both
  reused unchanged from `commons/repositories/db/`, spec 0007 AD-7 — no new
  query code), and asks the agent to judge each.
- `models/retrieval_judge_item_result.py` — `RetrievalJudgeItemResult`, the
  per-question verdict returned by the service.
- `wiring.py` + `main.py` — lazy DI builders and an `argparse` entry point
  registered as `evaluate-retrieval-judge` in `[project.scripts]`. No
  manifest, no `RunArtifactWriter`, no dry-run chain, no live dashboard: it
  prints verdicts and a share-clear percentage to stdout and exits.
- **(spec 0011 phase 2)** `label_main.py` — a second `argparse` entry point,
  `label-golden-set`, sharing `wiring.py`'s DI builders and `IngestorConfig`
  with the judge script above. Unlike the judge, it persists every verdict:
  it inserts one `labeling_runs` row per run (provenance: judge model, prompt
  version, arm depths, shuffle seed, corpus commit/comma count), then writes
  one `quiz_labelings` row plus its `quiz_comma_labels` children per labeled
  question through a new, insert-only `GoldenSetWriteRepository`
  (`repositories/golden_set_write_repository.py` — `INSERT` statements only,
  no `UPDATE`/`DELETE`/DDL). It still carries none of the `ingest` CLI's
  manifest/dry-run machinery (same reasoning as (1) above still applies: a
  labeling pass is re-run by hand, not scheduled), and it still needs a
  distinct agent — `CommaLabelerAgent` (`agents/comma_labeler/`, its own
  `dto/` and prompt file) rather than widening `RetrievalJudgeResponse`,
  since `BaseAgent` binds one `output_type` per class.

`wiring.py` reuses `guidami_ai_patente_ingestor.configs.IngestorConfig` for the
Postgres connection, table names, `agents_dir`, and the OpenRouter provider,
rather than introducing a settings class of its own — the module's one
deliberate cross-package dependency, accepted to avoid duplicating
`.env`/YAML settings loading for a tool with no config surface of its own.

The module has no built-in multi-run averaging: running it several times and
eyeballing the spread (for judge-stability checks) versus running it once with
a larger `--n` (for a final estimate) are both just re-invocations of the same
script with different flags, not a feature the service implements.

## Alternatives considered

- **A new mode of `ingest evaluate retrieval`** (e.g. `--judge`) — rejected:
  every existing mode of that command inherits manifest/dry-run/`RunArtifactWriter`
  machinery built for an unattended, auditable, CI-run harness. Reusing it here
  would mean building a manifest type and a dry-run chain for a script whose
  whole point is to run by hand a handful of times, and would put an
  LLM-calling, real-cost operation inside a command spec 0007 (FR-8) requires
  to make zero network calls.
- **Amend spec 0007's Non-Goals to no longer exclude an LLM judge** — rejected
  on the user's explicit instruction. The Non-Goal is left as written; this ADR
  is the record of why building the judge elsewhere does not contradict it.
- **A CLI-only component under `guidami_ai_patente_ingestor/cli/`** —
  rejected by the same test `.claude/rules/cli-structure.md` already applies to
  the read repositories (AD-7 in spec 0007): "is this used by anything other
  than the CLI?" This tool isn't used by the CLI at all.
- **Built-in multi-run averaging in the service** (run `n` samples `m` times,
  return a mean) — rejected on the user's explicit instruction: the harness
  will be re-run by hand for stability checks, then once with a larger sample;
  a averaging feature would solve a problem nobody asked for.

## Consequences

- The judge can be exercised and iterated on without touching spec 0007's
  harness at all — no manifest type to add, no dry-run chain to extend, no
  risk of breaking FR-8's "no LLM/network call" guarantee for the existing
  command.
- Two independent measurement tools now exist over the same corpus
  (`ingest evaluate retrieval` and `evaluate-retrieval-judge`), and nothing
  in the code enforces they agree on shared vocabulary (e.g. both call their
  retrieval depth `k`, but only informally). A future reader must consult
  both this ADR and spec 0007 to understand why.
- `retrieval_evaluation/` depends on `guidami_ai_patente_ingestor.configs`
  for settings — a top-level package importing another top-level package's
  config, an asymmetry from every other sibling script
  (`parsers/`/`scrapers/`/`test_data_sampler/`), which either take no config
  or take a narrower slice of it. Acceptable while this stays a single
  exploratory script; would need revisiting if it grows a config surface of
  its own.
- Cost/observability: the judge's LLM calls are tracked through the same
  `QueuedLlmCallTracker`/`LlmCallLogRepository` path as every other agent
  call, so its OpenRouter spend is visible in `llm_call_logs` like any other
  agent, even though it runs outside the `ingest` CLI.
- **(spec 0011 phase 2)** This module is no longer artifact-free. The
  original framing above — "exploratory measurement... closer in spirit to a
  one-shot script than to a run-artifact-producing harness" — described
  `evaluate-retrieval-judge` accurately and still does today: that script
  writes nothing but an optional `results.json`. It no longer describes the
  module as a whole: `label-golden-set` persists every labeling to Postgres,
  by design, as the module's whole purpose (the golden set is meant to
  outlive the run that produced it, unlike the judge's spot-check verdicts).
  What did **not** change is the reason this module sits outside `cli/` and
  outside `ingest evaluate retrieval`: no manifest type, no `--dry-run`
  chain, no `RunArtifactWriter` machinery — persistence here means three
  Postgres tables written by an insert-only repository, not the CLI's
  audited-run-artifact shape those flags exist for. The placement decision
  in this ADR stands unchanged; only the "writes no persistent artifact"
  characterization is retired.
