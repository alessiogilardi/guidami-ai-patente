from pathlib import Path

import pytest
from pydantic_settings import SettingsConfigDict

from commons.configs import BaseConfig


class _SampleConfig(BaseConfig):
    """Throwaway settings class: keeps the unit test decoupled from any real consumer."""

    model_config = SettingsConfigDict(yaml_file="configs/sample_config.yaml")

    name: str = "default"
    size: int = 1


class _NoYamlConfig(BaseConfig):
    """Settings class with no `yaml_file` configured at all."""

    name: str = "default"


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_reads_base_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "configs").mkdir()
    _write(tmp_path / "configs/sample_config.yaml", "name: from_base\nsize: 7\n")
    monkeypatch.chdir(tmp_path)

    config = _SampleConfig.load()

    assert config.name == "from_base"
    assert config.size == 7


def test_override_yaml_layers_over_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "configs").mkdir()
    _write(tmp_path / "configs/sample_config.yaml", "name: from_base\nsize: 7\n")
    _write(tmp_path / "configs/override.yaml", "name: from_override\n")
    monkeypatch.chdir(tmp_path)

    config = _SampleConfig.load("configs/override.yaml")

    assert config.name == "from_override"
    assert config.size == 7


def test_env_wins_over_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "configs").mkdir()
    _write(tmp_path / "configs/sample_config.yaml", "name: from_base\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NAME", "from_env")

    assert _SampleConfig.load().name == "from_env"


def test_class_without_yaml_file_still_constructs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _NoYamlConfig.load().name == "default"


def test_is_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = _NoYamlConfig.load()

    with pytest.raises(Exception):
        config.name = "mutated"  # pyright: ignore[reportAttributeAccessIssue]
