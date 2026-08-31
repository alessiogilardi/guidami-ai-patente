from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class BaseConfig(BaseSettings):
    """Base class for every root, self-loading settings class in the project."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        env_nested_delimiter="__",
        env_file=".env",
    )

    _config_override_file: ClassVar[Path | None] = None
    """Set by `load()` on a dynamically-created subclass, never on `BaseConfig` or a
    concrete subclass directly. Points `settings_customise_sources` at an extra,
    higher-precedence YAML layered on top of the subclass's own base YAML (its
    `model_config['yaml_file']`, if any). See ADR 0006 for the profile-switching use
    case this originally shipped for.
    """

    @classmethod
    def load(cls, config_override: Path | str | None = None, **init_kwargs: Any) -> Self:
        """Builds the config, optionally layering `config_override` over the base YAML.

        `config_override` only needs to set the fields that actually differ from the
        class's own base YAML — it becomes its own `YamlConfigSettingsSource`, placed
        between env/.env and the base YAML, so fields it does not mention still fall
        through. `init_kwargs` are forwarded to the constructor unchanged (highest
        precedence).

        Note: with `config_override` set, the returned instance is of a dynamically
        created subclass carrying it as `_config_override_file`, not of `cls` itself.
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
        return subclass(**init_kwargs)  # pyright: ignore[reportCallIssue, reportArgumentType, reportReturnType]

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
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]
        override_file = getattr(settings_cls, "_config_override_file", None)
        if override_file is not None:
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=override_file))
        sources.append(YamlConfigSettingsSource(settings_cls))
        return tuple(sources)
