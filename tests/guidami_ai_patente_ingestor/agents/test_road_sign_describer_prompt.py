"""Structural contract of configs/agents/road_sign_describer.yaml (spec 0023, FR-2/FR-3)."""

from pathlib import Path

import pytest
import yaml

_CONFIG = Path(__file__).parents[3] / "configs" / "agents" / "road_sign_describer.yaml"


@pytest.fixture(scope="module")
def config() -> dict[str, object]:
    return yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))


def test_model_is_gemini_3_8_flash(config: dict[str, object]) -> None:
    assert config["model_name"] == "openrouter/google/gemini-3.8-flash"


def test_system_prompt_explains_both_answer_labels(config: dict[str, object]) -> None:
    system = str(config["system"])
    assert "(Vero)" in system
    assert "(Falso)" in system


def test_labeled_statements_stay_inside_the_data_tag(config: dict[str, object]) -> None:
    user = str(config["user"])
    assert "<contesti_quiz>\n$contexts_block\n</contesti_quiz>" in user
    assert "<contesti_quiz>" in str(config["system"]), "the system prompt must name the data tag"


def test_output_field_order_is_unchanged(config: dict[str, object]) -> None:
    user = str(config["user"])
    positions = [user.index(f'"{key}"') for key in ("visual_analysis", "name", "description")]
    assert positions == sorted(positions)


def test_three_case_taxonomy_is_kept(config: dict[str, object]) -> None:
    user = str(config["user"])
    assert "singolo segnale stradale isolato" in user
    assert "scena di guida" in user
    assert "Due o più segnali abbinati o in sequenza" in user
