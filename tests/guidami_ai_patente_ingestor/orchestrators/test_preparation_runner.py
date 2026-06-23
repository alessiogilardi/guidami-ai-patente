"""Test per run_preparation (runner generico, per-source)."""

from pathlib import Path
from unittest.mock import MagicMock

from commons.flowstep import Flow
from guidami_ai_patente_ingestor.orchestrators import run_preparation


def test_skips_flow_run_when_out_path_exists_and_force_is_false(tmp_path: Path) -> None:
    out_path = tmp_path / "enriched" / "cds" / "articles.json"
    out_path.parent.mkdir(parents=True)
    out_path.write_text("[]", encoding="utf-8")

    flow = MagicMock(spec=Flow)
    run_preparation(flow, out_path, force=False)

    flow.run.assert_not_called()


def test_runs_flow_when_out_path_does_not_exist(tmp_path: Path) -> None:
    out_path = tmp_path / "enriched" / "cds" / "articles.json"

    flow = MagicMock(spec=Flow)
    run_preparation(flow, out_path, force=False)

    flow.run.assert_called_once_with()


def test_runs_flow_when_force_is_true_even_if_out_path_exists(tmp_path: Path) -> None:
    out_path = tmp_path / "enriched" / "cds" / "articles.json"
    out_path.parent.mkdir(parents=True)
    out_path.write_text("[]", encoding="utf-8")

    flow = MagicMock(spec=Flow)
    run_preparation(flow, out_path, force=True)

    flow.run.assert_called_once_with()
