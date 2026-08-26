"""FR-14: a judge the batch never used is a warning, never a startup abort."""

import logging
from dataclasses import dataclass

import pytest

from guidami_ai_patente.services import JudgeCoherenceChecker


@dataclass
class _GoldenSetDouble:
    versions: list[str] | None = None
    error: Exception | None = None

    def distinct_prompt_versions(self) -> list[str]:
        if self.error is not None:
            raise self.error
        return self.versions or []


@dataclass
class _EpochDouble:
    prompt_version: str = "aaaaaaaaaaaaaaaa"
    judge_model: str = "openrouter/google/gemini-2.5-flash-lite"


@dataclass
class _StackDouble:
    epoch: _EpochDouble


def _checker(golden_set: _GoldenSetDouble) -> JudgeCoherenceChecker:
    checker = object.__new__(JudgeCoherenceChecker)
    checker.golden_set = golden_set  # type: ignore[assignment]
    checker.labeling_stack = _StackDouble(_EpochDouble())  # type: ignore[assignment]
    return checker


def test_a_matching_version_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        _checker(_GoldenSetDouble(versions=["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"])).check()

    assert caplog.records == []


def test_an_empty_golden_set_is_not_a_divergence(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        _checker(_GoldenSetDouble(versions=[])).check()

    assert caplog.records == []


def test_a_divergent_version_warns_naming_both_sides(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        _checker(_GoldenSetDouble(versions=["bbbbbbbbbbbbbbbb"])).check()

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "aaaaaaaaaaaaaaaa" in message and "bbbbbbbbbbbbbbbb" in message


def test_a_failing_check_does_not_abort_startup(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        _checker(_GoldenSetDouble(error=RuntimeError("database unreachable"))).check()

    assert len(caplog.records) == 1
    assert "database unreachable" in caplog.records[0].getMessage()
