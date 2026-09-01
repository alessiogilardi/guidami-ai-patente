from pathlib import Path

import pytest

from commons.ai.observability import ObservabilityConfig, TrackerBackend


def test_defaults_without_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    config = ObservabilityConfig.load()

    assert config.enabled is True
    assert config.backend is TrackerBackend.POSTGRES
    assert config.table == "llm_call_logs"
    assert config.queue_join_timeout_s == 10.0


def test_reads_committed_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/observability_config.yaml").write_text(
        "enabled: false\nbackend: postgres\ntable: other_logs\nqueue_join_timeout_s: 2.5\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = ObservabilityConfig.load()

    assert config.enabled is False
    assert config.table == "other_logs"
    assert config.queue_join_timeout_s == 2.5


def test_env_prefix_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/observability_config.yaml").write_text(
        "enabled: true\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_TRACKING_ENABLED", "false")

    assert ObservabilityConfig.load().enabled is False


def test_backend_value_is_derived_from_member_name() -> None:
    assert TrackerBackend.POSTGRES == "postgres"
