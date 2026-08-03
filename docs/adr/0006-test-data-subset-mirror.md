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
  `IngestorConfig()`/`build_parser(config)` are constructed (the command
  parser itself is config-driven, so the switch must happen first).
  `_load_yaml_overrides` then `yaml.safe_load`s that file into a plain
  `dict` and `main()` passes it as `IngestorConfig(**overrides)`. Pydantic-
  settings already deep-merges `init_settings` (highest precedence) with
  the always-loaded default `configs/ingestor_config.yaml` — verified
  empirically for both a nested `BaseModel` field (`postgres`, merging
  `host` from one source with `user`/`password` from another) and a plain
  `dict[str, str]` field (`layers`, replaced wholesale by whichever source
  provides it). So `configs/ingestor_config.test-data.yaml` only needs to
  list the fields that actually differ — `layers` and `quiz_images_dir` —
  not a full duplicate of every field; every other field (`sources`,
  `postgres`, `embedding`, table names, `rca_ranges`, ...) is inherited
  straight from the base yaml, with nothing to keep in sync. `IngestorConfig`
  itself required **no changes** — `settings_customise_sources` still always
  loads `configs/ingestor_config.yaml` as the yaml source; the override is
  layered on top via `init_settings`, the constructor argument path
  pydantic-settings already gives top precedence.
  See the "Alternate config profile via a delta yaml, merged through
  `init_settings`" row in `docs/patterns.md`.
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
  into `data/test-data/parsed/quiz-patente-ab/images/`. Placed as a flat
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
- `data/test-data/parsed/`'s images subset must be regenerated
  (`uv run sample-test-data`) whenever `data/parsed/quiz-patente-ab/images/`
  changes; there is no mechanical check that the two stay in sync — a
  stale test-data image set would only surface as a missing-file error the
  next time `sample-test-data` re-samples a question referencing a removed
  image.

*Referenced from `docs/layout.md`, `docs/patterns.md`.*
