"""Pins comma-labeler's num_retries (spec 0014, FR-5)."""

import os
from pathlib import Path

import yaml

from commons.ai.agents import AgentConfig


def test_comma_labeler_num_retries_is_five() -> None:
    """Verifies the comma labeler's retry budget is 5.

    Two retry-triggering conditions (repeated ordinal, out-of-range ordinal) share
    this budget, raised from the shared default (3) to leave room for both failure
    modes.
    """
    agents_dir = Path(os.environ["AGENTS_DIR"])
    raw = yaml.safe_load((agents_dir / "comma_labeler.yaml").read_text(encoding="utf-8"))
    config = AgentConfig(**raw)

    assert config.num_retries == 5
