# ADR 0006: A `data/test-data/` Subset Mirror, Selected via a `--config` Profile

## Status

Proposed

## Context

Running `ingest prepare`/`ingest index` against the full corpus (`data/parsed/`:
266 CdS articles, the full CAP/RCA range, the full Regolamento, 715 quiz
questions with ~4100 images) is slow and, for the quiz path, costs real LLM
calls (`ImageDescriptionEnricher`/`NormReferenceEnricher`, ADR 0005). There
was no way to exercise cleaning/enrichment/indexing end-to-end against a
small, fast, cheap subset — every local run either used the full corpus or
required a hand-rolled one-off setup.

Three design questions had to be resolved before implementing this:

1. How does the pipeline get pointed at a different data root than
   `data/`? `IngestorConfig()` (`configs/ingestor_config.py`) always loaded
   the same hardcoded `configs/ingestor_config.yaml`, and the `ingest` CLI's
   command parser is itself built *from* that config
   (`build_parser(config)` in `cli/main.py`), so any switch has to happen
   before the parser exists.
2. Does the subset write to the same Postgres tables as a normal run, or an
   isolated set?
3. Is the subset generated once by hand, or by a re-runnable, registered
   script?

## Decision

- **Config switch**: `cli/main.py::_parse_config_override` pre-parses a
  `--config PATH` flag out of `argv` with a minimal
  `argparse.ArgumentParser(add_help=False).parse_known_args(...)`, *before*
  `IngestorConfig`/`build_parser(config)` are constructed (the command
  parser itself is config-driven, so the switch must happen first). `main()`
  then calls `IngestorConfig.load(config_override)` — a classmethod on
  `IngestorConfig` (`configs/ingestor_config.py`) that, when `config_override`
  is given, dynamically creates a one-off subclass carrying it as a `ClassVar`
  (`_config_override_file`) and instantiates that instead. `settings_customise_sources`
  reads that `ClassVar` and, if set, inserts a **second**
  `YamlConfigSettingsSource(settings_cls, yaml_file=config_override)` into the
  sources tuple — between `env`/`.env` and the always-present base-yaml source
  — so the override file is a genuine, independent pydantic-settings source,
  not a dict we parse ourselves and smuggle in through `init_settings`
  (`init_settings` stays reserved for real constructor kwargs, e.g. in tests).
  Precedence: `init_settings` > `env`/`.env` > override yaml (`load()`) > base
  yaml. Pydantic-settings deep-merges these already — verified empirically for
  both a nested `BaseModel` field (`postgres`, merging `host` from one source
  with `user`/`password` from another) and a plain `dict[str, str]` field
  (`layers`, replaced wholesale by whichever source provides it). So
  `configs/ingestor_config.test-data.yaml` only needs to list the fields that
  actually differ — `layers` and `quiz_images_dir` — not a full duplicate of
  every field; every other field (`sources`, `postgres`, `embedding`, table
  names, `rca_ranges`, ...) is inherited straight from the base yaml, with
  nothing to keep in sync. See the "Alternate config profile via a second,
  higher-precedence yaml source" row in `docs/patterns.md`.
- **DB target**: the test-data profile keeps the same `postgres` connection
  and the same table names (`articles`, `article_commas`,
  `quiz_questions`) as the default profile. Running `ingest index` against
  the subset writes into the same tables a normal run would — no schema
  change, no isolation. `ingest reset knowledge`/`ingest reset quiz` is the
  mechanism to clear between a subset run and a full run.
- **Sampling**: `src/test_data_sampler/sampler.py`, registered as
  `uv run sample-test-data [--count N] [--seed N]` (default: 20 elements
  per source, seed 42). Reads `data/parsed/{cds,cap,reg,quiz-patente-ab}`,
  writes a `random.Random(seed).sample(...)`-selected subset to
  `data/test-data/parsed/...`, and — for quiz — copies only the images
  actually referenced by the sampled questions' `sub_questions[].image`
  into `data/test-data/parsed/quiz-patente-ab/images/` (moved to
  `data/test-data/quiz-images/`, source now `data/quiz-images/` — see ADR
  0008; this ADR's decision, copy only the referenced subset, is
  unchanged). Placed as a flat
  module in its own top-level package (sibling to `parsers/`/`scrapers/`,
  same `C901`-exempt "one-shot script" tier), not inside
  `guidami_ai_patente_ingestor/`, following `scrapers/rca_extract.py`'s
  existing shape (hardcoded source/dest path constants, raw-dict JSON
  manipulation, a testable pure function plus a thin `main()`).
- **Data-tree treatment**: `data/test-data/parsed/` and
  `data/test-data/cleaned/` are committed to git, mirroring the main tree's
  `data/parsed/`/`data/cleaned/`; `data/test-data/enriched/` is
  `.gitignore`d for the identical reason `data/enriched/` already is (ADR
  0005 — non-deterministic, cost-bearing-to-regenerate LLM output).
  > **No longer accurate.** ADR 0005 was superseded by ADR 0012 on
  > 2026-08-06: neither `data/enriched/` nor `data/test-data/enriched/` is
  > gitignored any more, and both are committed. The mirroring principle this
  > bullet states is unaffected — the two trees are still treated identically,
  > just on the other side of the line.

## Alternatives considered

- **New `--config` argparse flag defined on the command-driven parser
  itself**: rejected — `build_parser(config)` already consumes `config` to
  populate `choices=` for `--source` etc., so the config must be resolved
  *before* that parser is built; a flag defined on the parser it precedes
  is a circular dependency. The pre-parse (`parse_known_args`) approach
  avoids this by resolving `--config` in a separate, minimal parser first.
- **Env-var-driven yaml *file swap*** (`IngestorConfig.settings_customise_sources`
  reading which yaml file to load from an env var set by `--config`,
  first implementation attempt): rejected after empirically confirming
  `init_settings` already deep-merges with the base yaml — the file-swap
  approach requires the override yaml to be a **full** duplicate of every
  field (swapping which file is the yaml source entirely discards the base
  yaml), reintroducing exactly the duplication-drift risk this ADR exists
  to avoid, plus a process-global `os.environ` mutation as a side channel
  for what both the CLI and `IngestorConfig` treat as an ordinary
  constructor argument.
- **Env-var override only, no `--config` flag** (e.g. a `.env.test` the
  user sources manually): considered simpler to implement, but pushes a
  manual, easy-to-forget shell step onto every invocation instead of one
  explicit, visible CLI argument; rejected in favor of the flag.
- **Read the override yaml into a plain `dict`, pass as `IngestorConfig(**overrides)`**
  (second implementation attempt, with the reading done either by hand via
  `yaml.safe_load` or via `commons.repositories.YamlRepository`): worked and
  kept the delta-yaml benefit, but conflated two different concepts —
  `init_settings` is meant for genuine caller-supplied constructor kwargs,
  not a second config file's content smuggled in through the same channel.
  `YamlRepository` specifically was also a poor fit: it exists to persist
  **model-shaped** data (Pydantic/dataclass/dict-with-a-known-shape), and
  its path-traversal safety check became vacuous the only way it could be
  wired for an arbitrary `--config PATH` (`LocalFileSystemClient(config_override.parent)`
  makes the base directory self-referential, so the check can never actually
  fail) — extra indirection bought no real safety. Rejected in favor of making
  the override file a first-class, independent `YamlConfigSettingsSource`
  inside `settings_customise_sources`, keeping `init_settings` for real kwargs
  only and reusing pydantic-settings' own yaml-reading code path.
- **A public `_yaml_file=...` init kwarg, mirroring `_env_file`** (proposed,
  never implemented): rejected after confirming empirically that
  `BaseSettings.__init__` does not special-case a `_yaml_file` kwarg the way
  it does `_env_file`/`_secrets_dir` — passing one raises `ValidationError`
  (`extra_forbidden`), and merely setting `yaml_file` in `model_config`
  without a `YamlConfigSettingsSource` wired into `settings_customise_sources`
  is silently inert (pydantic-settings itself warns about this). There is no
  built-in per-instantiation override for a custom-added source like ours.
- **Isolated DB target for the subset** (a `_test` suffix on table names,
  or a separate database): rejected for now — adds a schema/migration
  surface (`db/init.sql`) for a workflow that, in practice, is bookended by
  `ingest reset`. Revisit if subset runs and full runs ever need to coexist
  without resetting in between.
- **One-off manual subset generation** (a throwaway script, not registered):
  rejected — the full corpus in `data/parsed/` will change (re-scrapes,
  quiz PDF re-parses), and the subset needs to be regenerable on demand
  without re-deriving the sampling logic each time.

## Consequences

- `uv run ingest --config configs/ingestor_config.test-data.yaml prepare
  knowledge --source cds` (and the equivalent `index`/`prepare quiz`/`index
  quiz` invocations) now runs the exact same step chains as a full run,
  just against ~20 elements per source — fast local iteration without
  touching the full corpus.
- Every subset `index` run lands in the same tables a full run would;
  running both without an intervening `ingest reset` mixes subset and
  full-corpus rows in the same table with no way to distinguish them
  after the fact.
- `--config` generalizes past this one use case: any future alternate
  profile (a different Postgres target, a different embedding model, etc.)
  is just another delta yaml file — no further CLI or `IngestorConfig`
  plumbing needed, and no risk of drifting from the base yaml on fields
  the profile doesn't need to override.
- `data/test-data/quiz-images/`'s subset must be regenerated
  (`uv run sample-test-data`) whenever `data/quiz-images/` changes (paths
  moved by ADR 0008; the sync gap described here is unchanged); there is
  no mechanical check that the two stay in sync — a stale test-data image
  set would only surface as a missing-file error the next time
  `sample-test-data` re-samples a question referencing a removed image.

*Referenced from `docs/layout.md`, `docs/patterns.md`.*
