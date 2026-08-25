# Spec: `BaseConfig` — a shared base for root configuration classes

Date: 2026-08-25
Status: Design approved by user; not yet implemented.

## Context

The user proposed a draft `src/commons/configs/base_config.py` (`BaseConfig(BaseSettings)`)
intended to become the common base for configuration classes across the project. This spec
plans the integration — it does not implement it. The draft itself is not committed anywhere
and must not be used verbatim (see "Bugs found in the draft" below); it served only as the
starting point for this design.

Today, three classes in the project are root, self-loading `pydantic_settings.BaseSettings`
subclasses (constructed with no required external wiring — they read `.env`/env vars/YAML
themselves):

- `IngestorConfig` (`src/guidami_ai_patente_ingestor/configs/ingestor_config.py`) — already
  hand-rolls the exact mechanism `BaseConfig` is meant to generalize: a `load(config_override)`
  classmethod that, when given an override path, builds a dynamic one-off subclass carrying it
  as a `ClassVar`, plus a `settings_customise_sources` override implementing precedence
  `init > env/.env > override yaml > base yaml`. This exists to serve ADR 0006 (the
  `--config configs/ingestor_config.test-data.yaml` profile mechanism).
- `AppConfig` (`src/guidami_ai_patente/configs/app_config.py`) — the FastAPI app's root
  config, currently env/`.env`/init only, no YAML loading. ADR 0017 ("Proposed", not yet
  implemented) describes it eventually gaining `yaml_file="configs/app_config.yaml"` and
  `load()`-style construction identical to `IngestorConfig`'s, but the current code has neither.
- `OpenRouterConfig` (`src/commons/configs/open_router_config.py`) — a small `BaseSettings`
  holding `api_key: SecretStr`, `env_prefix="OPENROUTER_"`, no YAML. Always constructed
  zero-arg (`default_factory=OpenRouterConfig` inside `IngestorConfig`).

Every other class under a `configs/` folder in the project (`PostgresConnectionConfig`,
`EmbeddingClientConfig`, `AgentConfig`, `EvaluationConfig`, `LabelingConfig`,
`PipelineLayerConfig`, `SourceConfig`) is a plain `pydantic.BaseModel` value object, nested
inside one of the three root configs and populated by the root config's own settings sources
(env-nested-delimiter parsing, YAML, or literal in-code defaults) — not independently
self-loading. **These are explicitly out of scope for this migration**: an earlier version of
this design considered a second shared base (`FrozenConfig`) purely to deduplicate their
repeated `model_config = ConfigDict(frozen=True)`, but the user decided this isn't worth doing
— they remain plain `BaseModel` subclasses, unchanged.

### Documentation drift noticed during this design

`docs/second-brain/architecture.md` currently describes `PostgresConnectionConfig` as a
`BaseSettings`. The real code (and ADR 0017, which relies on it being a plain nested value
object populated via `AppConfig`'s `env_nested_delimiter="__"`) has it as a `BaseModel`. This
is a stale doc, not a pending decision — `second-brain:update` should correct it as part of
landing this migration.

## Bugs found in the user's draft

The draft `base_config.py` was evaluated empirically (installed `pydantic-settings==2.14.1`)
and found to have two silent, non-raising bugs, plus one redundancy. None of these are carried
into the design below.

1. **Dead override hook.** The draft names its hook `settings_customize_sources` (American
   spelling, with a "z"). `pydantic_settings.BaseSettings` calls `settings_customise_sources`
   (British spelling, with an "s") — confirmed via
   `hasattr(BaseSettings, 'settings_customize_sources') == False` against the installed
   package. With the draft's spelling, the entire custom source-composition logic (override
   YAML, base YAML) is unreachable: pydantic-settings silently falls back to its default source
   order (init, env, dotenv, file secrets) and no YAML is ever read, with no error raised
   anywhere. `IngestorConfig`'s existing hand-written implementation uses the correct spelling.
2. **`None` used as "not specified."** The draft's `_SectionedYamlConfigSettingsSource.__init__`
   declares `yaml_file: Path | str | None = None`. When `BaseConfig` appends the "base yaml"
   source without passing `yaml_file` explicitly, this default (`None`) is forwarded to
   `YamlConfigSettingsSource.__init__`. The installed `YamlConfigSettingsSource.__init__`
   distinguishes an explicit `None` from its own "not specified" sentinel (`DEFAULT_PATH`):
   only when the argument equals `DEFAULT_PATH` does it fall back to reading
   `settings_cls.model_config.get('yaml_file')`. Passing `None` explicitly — as the draft does
   — disables reading the class's configured `yaml_file` entirely, even if bug #1 above were
   fixed.
3. **Redundant custom source.** The draft's `_SectionedYamlConfigSettingsSource` reimplements
   YAML sub-section dot-notation traversal by hand. The installed `pydantic-settings` (2.14.1)
   already supports this natively: `YamlConfigSettingsSource`/`SettingsConfigDict` accept a
   `yaml_config_section` key (confirmed present in `SettingsConfigDict.__annotations__`), with
   its own `_traverse_nested_section` implementation that additionally handles YAML keys that
   are themselves literally dotted — a case the draft's hand-rolled splitter does not handle.

Verified empirically (see "Verification notes" below) that omitting `yaml_file` from a call to
the real `YamlConfigSettingsSource(settings_cls)` correctly falls back to
`model_config.get('yaml_file')`, and that a class with no `yaml_file` configured at all gets an
empty, error-free `yaml_data = {}` — i.e., `AppConfig()`/`OpenRouterConfig()` remain safe to
call with no YAML file configured after inheriting from `BaseConfig`.

## Design

### `BaseConfig`

New file: `src/commons/configs/base_config.py`.

```python
import logging
from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

logger = logging.getLogger(__name__)


class BaseConfig(BaseSettings):
    """Base class for every root, self-loading settings class in the project."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        env_nested_delimiter="__",
        env_file=".env",
    )

    _config_override_file: ClassVar[Path | None] = None
    """Set (on a dynamically-created subclass, never on `BaseConfig` or a concrete subclass
    directly) by `load()` to point `settings_customise_sources` at an extra, higher-precedence
    YAML source layered on top of the subclass's own base YAML (its `model_config['yaml_file']`,
    if any). See ADR 0006 for the profile-switching use case this originally shipped for
    (`IngestorConfig`'s `--config configs/ingestor_config.test-data.yaml`), and the ADR this
    spec's implementation will add for its extraction into this shared base.
    """

    @classmethod
    def load(cls, config_override: Path | str | None = None, **init_kwargs: Any) -> Self:
        """Builds the config, optionally layering `config_override` over the base YAML.

        `config_override` only needs to set the fields that actually differ from the class's
        own base YAML — it becomes its own `YamlConfigSettingsSource`, positioned between
        env/.env and the base YAML, so fields it doesn't mention still fall through
        (pydantic-settings deep-merges nested `BaseModel` fields across sources; plain fields
        are replaced wholesale by whichever source provides them — see ADR 0006).
        `init_kwargs` are forwarded to the constructor unchanged (highest precedence).

        Note: with `config_override` set, the returned instance is of a dynamically created
        subclass (carrying `config_override` as its `_config_override_file`), not of `cls`
        itself.
        """
        if config_override is None:
            return cls(**init_kwargs)  # pyright: ignore[reportCallIssue, reportArgumentType]
        if isinstance(config_override, str):
            config_override = Path(config_override)
        subclass = type(
            cls.__name__,
            (cls,),
            {"_config_override_file": config_override, "__module__": cls.__module__},
        )
        return subclass(**init_kwargs)  # pyright: ignore[reportCallIssue, reportArgumentType]

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Precedence: init > env/.env > override yaml (`load()`) > base yaml."""
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings]
        override_file = getattr(settings_cls, "_config_override_file", None)
        if override_file is not None:
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=override_file))
        sources.append(YamlConfigSettingsSource(settings_cls))
        return tuple(sources)
```

A subclass that needs a YAML sub-section (the original motivation for the draft's custom
source class) sets `yaml_config_section="ai.embedding.openai"` in its own `model_config` — the
plain, unparameterized `YamlConfigSettingsSource(settings_cls)` call above already reads both
`yaml_file` and `yaml_config_section` from `model_config` via pydantic-settings' own sentinel
fallback. No subclass of `BaseConfig` needs this today; it is documented here because it is the
reason the draft's custom source existed, and future subclasses may need it.

Re-exported from `src/commons/configs/__init__.py` alongside the existing `OpenRouterConfig`
and `PostgresConnectionConfig`.

### Migration matrix — all three known root `BaseSettings` classes

| Class | File | Change |
|---|---|---|
| `IngestorConfig` | `guidami_ai_patente_ingestor/configs/ingestor_config.py` | Extends `BaseConfig`. Removes its own `load()`, `settings_customise_sources()`, `_config_override_file` (all now inherited). `model_config` keeps only `yaml_file="configs/ingestor_config.yaml"` — `frozen`, `extra`, `env_nested_delimiter`, `env_file` drop as duplicates of `BaseConfig`'s (verified empirically: `SettingsConfigDict` merges additively across the MRO, a subclass's dict updates rather than replaces the parent's). |
| `AppConfig` | `guidami_ai_patente/configs/app_config.py` | Extends `BaseConfig`. `model_config` is removed entirely — with no `yaml_file` added (explicitly out of scope; ADR 0017's proposed `yaml_file="configs/app_config.yaml"` is separate, not-yet-decided future work), every key it previously declared is now a pure duplicate of `BaseConfig`'s. |
| `OpenRouterConfig` | `commons/configs/open_router_config.py` | Extends `BaseConfig`. `model_config` keeps only `env_prefix="OPENROUTER_"`; `extra` and `env_file` drop as duplicates. |

Neither `AppConfig` nor `OpenRouterConfig` has any call site that uses `.load(config_override)`
today (confirmed by repo-wide search — the only instantiation sites are `AppConfig()` in
`guidami_ai_patente/main.py`, `AppConfig(postgres=...)` in
`tests/guidami_ai_patente/api/routers/test_health.py`, and the `default_factory=OpenRouterConfig`
in `IngestorConfig`). Migrating them was a deliberate choice, not a functional need: with 3/3
known root config classes on `BaseConfig`, the user chose uniformity now over deferring the two
that currently gain no behavior from it — see "Project-wide rule" below, which formalizes this
so the next root config class doesn't reopen the question.

None of the three classes' nested `BaseModel` fields (`postgres`, `embedding`, `sources`,
`evaluation`, `labeling`, etc.) change.

### Verification notes (empirical, already run against the installed environment)

- `SettingsConfigDict` merge across MRO: a subclass declaring only `yaml_file=...` in its own
  `model_config`, on top of a parent declaring `frozen`/`extra`/`env_nested_delimiter`/`env_file`,
  ends up with the full union of both — confirmed by instantiating a two-level `BaseSettings`
  subclass pair and inspecting `Child.model_config`.
- A class with no `yaml_file` in `model_config` at all: `YamlConfigSettingsSource(settings_cls)`
  resolves `yaml_file_path = None` and `yaml_data = {}`, and the settings class still
  instantiates successfully from its other sources (env/init). This is what keeps
  `AppConfig()`/`OpenRouterConfig()` safe after inheriting `BaseConfig`'s
  `settings_customise_sources`, which unconditionally appends a base-YAML source.

## Testing plan (TDD)

- New `tests/commons/configs/test_base_config.py`: exercises `BaseConfig`'s mechanism directly
  against a small throwaway settings class defined in the test module (not against
  `IngestorConfig`/`AppConfig`, to keep the unit test decoupled from any one consumer). Covers:
  env-var override, `.env` loading, `load(config_override)` layering a second YAML over the
  base one (mirroring ADR 0006's own deep-merge expectation), and a class with no `yaml_file`
  configured still constructing successfully.
- New `tests/commons/configs/test_open_router_config.py`: minimal — env var sets `api_key`,
  and `OpenRouterConfig.load()` (inherited, unused in production code today) still returns an
  equivalent instance to `OpenRouterConfig()`.
- New `tests/guidami_ai_patente/configs/test_app_config.py`: minimal — same shape, confirming
  `AppConfig()` and `AppConfig.load()` behave identically post-migration, closing a
  pre-existing coverage gap (today `AppConfig` is only exercised indirectly through
  `tests/guidami_ai_patente/api/routers/test_health.py`).
- Existing `tests/guidami_ai_patente_ingestor/configs/test_ingestor_config.py` and
  `test_ingestor_config_load.py` are the regression gate for the `IngestorConfig` extraction:
  they must continue to pass unmodified, proving the refactor is behavior-preserving.

## Second Brain / architecture documentation impact

This migration is both a structural refactor (three existing classes change base class and
lose duplicated code) and a new, binding architectural rule, so it requires a
`second-brain:update` pass once implemented:

- A new ADR documenting the extraction of `BaseConfig` into `commons/configs/`, its precedence
  semantics, and that it **supersedes the mechanism ADR 0006 described locally on
  `IngestorConfig`** (ADR 0006 itself is not rewritten — it stays as the historical record of
  *why* the override mechanism exists; the new ADR records where it now lives).
- **Project-wide rule** (new, to `.claude/rules/code-conventions.md`): every root,
  self-loading `BaseSettings` configuration class in the project must extend
  `commons.configs.BaseConfig`, not `pydantic_settings.BaseSettings` directly. This is stated
  as a binding convention (not merely "this is what we did this one time") because, with this
  migration, all three known instances already comply — the rule exists so the next one doesn't
  reopen the question this spec's grilling session already settled.
- Correction of the stale `architecture.md` claim that `PostgresConnectionConfig` is a
  `BaseSettings` (see "Documentation drift noticed during this design" above).

## Explicitly out of scope

- Adding `yaml_file="configs/app_config.yaml"` to `AppConfig` (ADR 0017's proposal) — a
  separate, not-yet-decided feature, independent of this migration.
- Any change to the nested `BaseModel` value objects (`PostgresConnectionConfig`,
  `EmbeddingClientConfig`, `AgentConfig`, `EvaluationConfig`, `LabelingConfig`,
  `PipelineLayerConfig`, `SourceConfig`) — considered and explicitly rejected (a `FrozenConfig`
  shared base was proposed to deduplicate their repeated `ConfigDict(frozen=True)` and
  withdrawn by the user as not worth doing).
- Any change to how/where `IngestorConfig`, `AppConfig`, or `OpenRouterConfig` are constructed
  at their call sites (`cli/main.py`, `guidami_ai_patente/main.py`) — they keep calling
  `IngestorConfig.load(config_override)` / `AppConfig()` / `OpenRouterConfig()` exactly as
  today; only the base class and the location of the shared logic change.

## Branch / workspace note

This spec itself was written in an isolated git worktree/branch
(`worktree-base-config-migration-design`), per explicit instruction, and is pushed to the
remote once written. The user's own draft `base_config.py` (on `feat/backend`, untracked) was
used only as the starting point for this design and is not copied verbatim — implementation,
when requested, starts fresh from the corrected design above, in its own worktree/branch.
