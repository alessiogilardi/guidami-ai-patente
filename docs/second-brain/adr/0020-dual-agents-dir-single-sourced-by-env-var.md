# ADR 0020: `agents_dir` Stays Declared on Both `IngestorConfig` and `LabelingConfig`, Single-Sourced by One Defaultless Env Var

## Status

Proposed

## Context

Spec 0012's design (`docs/superpowers/specs/2026-08-24-quiz-flow-api-design.md`,
AD-27) established that the labeling judge's `agents_dir` — the directory its agent
YAML is loaded from — must resolve identically for the batch harness
(`guidami_ai_patente_ingestor`) and the future FastAPI app's live judge, because
`prompt_version` is a hash of the loaded prompt text: two deployments resolving
different files would silently produce a permanent 100% cache miss against
`labeling_runs` (AD-22). AD-27's original implementation clause read this as "no
duplicated *field*" and called for **deleting** `IngestorConfig.agents_dir` entirely
once `LabelingConfig.agents_dir` existed, leaving exactly one field in the whole
codebase.

That clause over-reached. `guidami_ai_patente_ingestor/orchestrators/quiz_flows.py:344`
loads the quiz *enrichment* agents (`road_sign_describer`, `norm_reference_describer`)
from `config.agents_dir` — prompts that describe road signs and cross-reference norms
for quiz enrichment, never labeled or judged, and therefore never part of the labeling
judge's configuration epoch. Routing that unrelated reader through
`config.labeling.agents_dir` would make an enrichment-pipeline failure look like a
labeling-config problem, and would force `guidami_ai_patente_ingestor.configs` to
import `labeling.configs` for a directory path that has nothing to do with labeling.

This is quiz-flow-api-phase1 plan decision D2 (with D10 filing the errata against
AD-27's letter, D11 adding the offline agreement check, D16 pinning the
nested-`BaseSettings` env-routing behavior this design depends on) — implemented in
Task 3.

## Decision

Keep `agents_dir: Path` declared on **both** `IngestorConfig`
(`guidami_ai_patente_ingestor/configs/ingestor_config.py`) and `LabelingConfig`
(`labeling/configs/labeling_config.py`, itself moved out of
`guidami_ai_patente_ingestor/configs/` in the same task). Both fields are:

- **defaultless** (`Field(validation_alias=AliasChoices("AGENTS_DIR", "agents_dir"))`,
  no `default=`) — a missing `AGENTS_DIR` is a loud `ValidationError` at construction,
  never a silent fallback to a stale default;
- **aliased to the exact same environment variable**, `AGENTS_DIR`.

The single-source guarantee comes from the one defaultless env var both fields read,
not from collapsing them into one shared field. Each reader keeps importing only the
config root it already depends on:

- `retrieval_evaluation/wiring.py`'s `build_agent` (retrieval judge) and
  `build_comma_labeler_config` (the judge itself) read `config.labeling.agents_dir` —
  their prompt hash **is** the configuration epoch.
- `guidami_ai_patente_ingestor/orchestrators/quiz_flows.py:344` keeps reading
  `config.agents_dir` unchanged — its prompts enter no epoch.

`configs/ingestor_config.yaml` no longer has an `agents_dir:` key (removing the
literal duplicate default that motivated AD-27 in the first place); the equivalent
non-epoch defaults for `LabelingConfig` live in the new `configs/labeling.yaml`,
which also omits `agents_dir` for the same reason. `.env.example` documents
`AGENTS_DIR=configs/agents` as the one place a developer sets it.

Because divergence is now structurally impossible only *within* one deployment (both
roots read the same process environment), not across two separately-deployed
processes with different `.env` files, `ingest status` also gained an explicit,
offline `StatusInspector` readiness check
(`_agents_dir_agreement_readiness`, `guidami_ai_patente_ingestor/cli/services/status/
status_inspector.py`) that reports `BLOCKED` if `config.agents_dir !=
config.labeling.agents_dir` ever resolve differently — e.g. if a later stray
`agents_dir:` key were added back to only one of the two YAML files. This is the
offline, in-process counterpart of AD-23's DB-backed startup warning (which checks
whether the *current process's* `prompt_version` matches anything ever recorded in
`labeling_runs` — a different, cross-deployment risk that no in-process check can
cover).

`LabelingConfig` is also a `BaseSettings` nested inside `IngestorConfig`
(`labeling: LabelingConfig = Field(default_factory=LabelingConfig)`), and
`IngestorConfig` sets `env_nested_delimiter="__"`. This was pinned with a dedicated
test (D16) rather than assumed: a `LABELING__DENSE_K` environment variable could
either route through `LabelingConfig`'s own settings sources (nested `agents_dir`
still resolves from `AGENTS_DIR`) or get validated as a plain nested model (nested
`agents_dir` would be absent, breaking every `ingest` command for anyone with a
`LABELING__*` variable set) — pydantic-settings' actual behavior here is the former,
confirmed by `tests/guidami_ai_patente_ingestor/configs/test_ingestor_config.py::
test_a_nested_env_override_does_not_break_the_labeling_config`.

## Alternatives considered

- **Delete `IngestorConfig.agents_dir`, keep only `LabelingConfig.agents_dir`** (AD-27's
  original letter): rejected — this is what D2 amends. It would force
  `quiz_flows.py`'s enrichment-agent loader, which has nothing to do with the labeling
  judge, to import and depend on `labeling.configs.LabelingConfig` purely to resolve an
  unrelated directory path, and would make an enrichment-pipeline failure surface as a
  labeling-config error.
- **One shared `AgentsDirConfig` value object embedded in both roots**: rejected as
  unnecessary ceremony — a `Path` with a validation alias needs no wrapper type, and a
  shared embedded model would still need the same defaultless-env-var discipline to
  avoid the exact divergence risk this decision addresses; it buys nothing over two
  independently-declared fields reading the same variable.
- **A module-level constant or a process-wide singleton for `agents_dir`**: rejected —
  breaks this repo's "config loaded once at the entry point, no global state"
  convention (`~/.claude/rules/python/architecture.md`) and both `IngestorConfig` and
  the future `AppConfig` (spec 0012) are already `BaseSettings` roots; a singleton
  would be a second, competing source of truth.

## Consequences

- Two config roots each still need one line to declare `agents_dir` — a small, visible
  cost, paid once, in exchange for zero coupling between the labeling judge's
  configuration epoch and the unrelated quiz-enrichment pipeline.
- Divergence *within* one running deployment is structurally impossible (one env var,
  two defaultless readers). Divergence *across* two deployments with different `.env`
  files is not addressed by this decision — that residual risk is AD-23's job (a
  DB-backed startup warning), not this one's.
- `ingest status` now reports a genuine, offline, no-DB/no-LLM signal
  (`command="config", entity="agents_dir"`) if the two fields are ever pointed at
  different directories by a future stray YAML key — a defense-in-depth check for a
  failure mode the env-var design otherwise only prevents by convention.
- AD-27 (`docs/superpowers/specs/2026-08-24-quiz-flow-api-design.md`) still needs its
  own dated errata block quoting this change (plan decision D18) — filed by the
  quiz-flow-api-phase1 plan's Task 11, not by this task. This ADR records the
  as-implemented decision for the Second Brain independently of that spec-document
  update.
