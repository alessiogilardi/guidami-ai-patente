# ADR 0021: `BaseConfig` Lands as a Partial Migration, `ObservabilityConfig` Its First Adopter

## Status

Proposed

## Context

Before this change, `IngestorConfig` (`guidami_ai_patente_ingestor/configs/ingestor_config.py`)
was the only root, self-loading `pydantic-settings` class in the project — it owns
its own `load(config_override=None, **init_kwargs)` classmethod and
`settings_customise_sources` override implementing the profile-switching
precedence (init > env/.env > override yaml > base yaml, ADR 0006). `OpenRouterConfig`
(`commons/configs/open_router_config.py`) is a second, simpler `BaseSettings`
(`env_prefix="OPENROUTER_"`, no yaml source, no `load()`/override machinery).

This task introduced `commons/ai/observability/configs/observability_config.py`
(`ObservabilityConfig`), which needed the same self-loading shape `IngestorConfig`
already had — `enabled`/`backend`/`table`/`queue_join_timeout_s`, loaded from
`configs/observability_config.yaml` and `LLM_TRACKING_*` env vars — but
duplicating `IngestorConfig.load`/`settings_customise_sources` verbatim a second
time would leave the exact same ~40 lines in two places with no shared home, and
copy forward any future fix to the loading logic into only one of the two
subclasses. A full three-way migration (`IngestorConfig`, `OpenRouterConfig`, and
the new `ObservabilityConfig` all rebased onto one shared base) is a separate,
larger piece of work — already scoped as its own design,
`docs/superpowers/specs/2026-08-25-base-config-migration-design.md`, developed on
a different branch (`worktree-base-config-migration-design`) not present in this
branch's history. Blocking `ObservabilityConfig` on that full migration landing
first would have coupled two independent efforts for no benefit to either.

## Decision

Extract the shared shape into `commons/configs/base_config.py::BaseConfig`, a
`BaseSettings` subclass carrying:

- `model_config = SettingsConfigDict(frozen=True, extra="ignore",
  env_nested_delimiter="__", env_file=".env")`.
- `load(config_override: Path | str | None = None, **init_kwargs) -> Self` —
  when `config_override` is given, dynamically subclasses `cls` to carry it as a
  `ClassVar[Path | None]` (`_config_override_file`), exactly as
  `IngestorConfig.load` already did, so the override becomes its own
  `YamlConfigSettingsSource` layered between env/.env and the subclass's own
  base yaml.
- `settings_customise_sources`, implementing that same precedence generically.

Only `ObservabilityConfig(BaseConfig)` adopts it in this change.
`IngestorConfig` and `OpenRouterConfig` are **explicitly not migrated** — both
keep their own independent `BaseSettings` implementations unchanged. This is a
deliberate **partial landing**: `BaseConfig` exists and is proven correct by a
real, tested adopter, but the migration of the two pre-existing config classes
onto it is left to the separate design already scoped for that work.

## Alternatives considered

- **Duplicate `IngestorConfig`'s `load`/`settings_customise_sources` into
  `ObservabilityConfig` directly, no shared base**: rejected — the two
  implementations would drift the moment either gained a bugfix or a new
  source, and `ObservabilityConfig` needs the identical precedence contract, not
  a variant of it.
- **Block this task on the full `base-config-migration-design` migration
  landing first, so every root config adopts `BaseConfig` in one change**:
  rejected — that design is separate, larger-scoped work being developed
  independently on its own branch; making `ObservabilityConfig` wait on it
  would couple an unrelated observability simplification to that migration's
  own timeline and review, and this module is specifically meant to stay
  removable/addable in one piece.
- **Migrate `OpenRouterConfig` onto `BaseConfig` now too, since it is the
  simpler of the two pre-existing classes**: rejected for this change — even
  the simpler migration is better done as one deliberate pass across every
  adopter (covered by the referenced design) than piecemeal, so the eventual
  migration has one clear "before" state to diff against, not a partially
  migrated one.

## Consequences

- `commons/configs/BaseConfig` exists and is exercised by a real caller
  (`ObservabilityConfig`, loaded once at the CLI entry point via
  `ObservabilityConfig.load()` in `cli/main.py`, per the "config loaded once at
  entry point" rule) — proof the shared shape works before it is asked to
  absorb the two pre-existing, more complex config classes.
- `IngestorConfig` and `OpenRouterConfig` are **unchanged** by this decision:
  they keep their own loading code, so this is not yet the single shared root-
  config base the codebase is ultimately headed toward. A reader must not
  assume every `commons/configs/` class self-loads the same way until the
  referenced migration design lands.
- The eventual migration of `IngestorConfig`/`OpenRouterConfig` onto
  `BaseConfig` is tracked at
  `docs/superpowers/specs/2026-08-25-base-config-migration-design.md` (on
  `worktree-base-config-migration-design`), not by this ADR — this ADR only
  records why `BaseConfig` was introduced now, ahead of that migration, and
  what its scope deliberately excludes.
