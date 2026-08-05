"""Tests for build_knowledge_cleaning_flow.

Per-element layer (`cleaned`): the flow rewires through
`LoadJsonStep`/`FilterAlreadyDoneStep`/`WriteJsonDirStep` (see
`docs/plans/2026-07-17--per-element-knowledge-layers.md`). Context enrichment
(`build_knowledge_enrichment_flow`) was removed by FR-16/AD-18 (T-13): see
`test_knowledge_flows.py::test_knowledge_flows_module_has_no_enrichment_factory`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from flowstep import Flow, FlowValidator
from flowstep.steps import ApplyStep
from pydantic import SecretStr

from commons.configs import PostgresConnectionConfig
from commons.utils import element_id
from guidami_ai_patente_ingestor.configs import IngestorConfig, SourceConfig
from guidami_ai_patente_ingestor.orchestrators import build_knowledge_cleaning_flow
from guidami_ai_patente_ingestor.orchestrators.steps.generic import (
    FilterAlreadyDoneStep,
    LoadJsonStep,
    WriteJsonDirStep,
)
from guidami_ai_patente_ingestor.services import LayerResolver

if TYPE_CHECKING:
    # See test_embedding_service.py for why this import is TYPE_CHECKING-guarded.
    from tests.conftest import RecordingProgressReporter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_config(**overrides: object) -> IngestorConfig:
    return IngestorConfig(
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password=SecretStr("unused"), dbname="unused"
        ),
        **overrides,  # type: ignore[arg-type]
    )


def _make_layer_resolver() -> LayerResolver:
    return MagicMock(spec=LayerResolver)


def _parsed_article_payload(number: str) -> dict:
    return {
        "number": number,
        "title": f"Articolo {number}",
        "commas": [{"number": "1", "text": f"Comma 1 art {number}."}],
        "url": f"https://example.com/art-{number}",
        "scraped_at": "2025-01-01T00:00:00",
        "repealed": False,
    }


def _cleaned_article_payload(number: str, source: str) -> dict:
    return {**_parsed_article_payload(number), "source": source}


# ---------------------------------------------------------------------------
# build_knowledge_cleaning_flow
# ---------------------------------------------------------------------------


def test_cleaning_flow_returns_flow_instance() -> None:
    flow = build_knowledge_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
        source="cds",
    )
    assert isinstance(flow, Flow)


def test_cleaning_flow_required_input_keys_is_empty_set() -> None:
    flow = build_knowledge_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
        source="cds",
    )
    report = FlowValidator().validate(flow)
    assert report.required_input_keys == set()


def test_cleaning_flow_build_with_validate_true_does_not_raise() -> None:
    flow = build_knowledge_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
        source="cds",
        validate=True,
    )
    assert isinstance(flow, Flow)


def test_cleaning_flow_unknown_source_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        build_knowledge_cleaning_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="quiz",
        )


def test_cleaning_flow_accepts_reg_source() -> None:
    flow = build_knowledge_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
        source="reg",
    )
    assert isinstance(flow, Flow)


def test_cleaning_flow_has_four_steps_load_clean_filter_write() -> None:
    flow = build_knowledge_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
        source="cds",
    )

    steps = flow.get_steps()
    assert len(steps) == 4
    assert isinstance(steps[0], LoadJsonStep)
    assert isinstance(steps[1], ApplyStep)
    assert isinstance(steps[2], FilterAlreadyDoneStep)
    assert isinstance(steps[3], WriteJsonDirStep)


def test_cleaning_flow_force_false_skips_already_cleaned_article(tmp_path: Path) -> None:
    """Decision 10/18: an article already present in `cleaned/` is not rewritten."""
    resolver = LayerResolver(
        layers={"parsed": str(tmp_path / "parsed"), "cleaned": str(tmp_path / "cleaned")},
        sources={"cds": SourceConfig(dir="cds", file="articles.json")},
    )
    parsed_path = resolver.path("parsed", "cds")
    parsed_path.parent.mkdir(parents=True)
    parsed_path.write_text(
        json.dumps([_parsed_article_payload("1"), _parsed_article_payload("2")]),
        encoding="utf-8",
    )

    cleaned_dir = resolver.dir("cleaned", "cds")
    cleaned_dir.mkdir(parents=True)
    already_done_id = element_id("cds", "1")
    sentinel_path = cleaned_dir / f"{already_done_id}.json"
    sentinel_path.write_text(json.dumps({"sentinel": True}), encoding="utf-8")

    config = _base_config(project_root=tmp_path)

    build_knowledge_cleaning_flow(
        config=config, layer_resolver=resolver, source="cds", force=False
    ).run()

    files = sorted(cleaned_dir.glob("*.json"))
    assert len(files) == 2
    # The pre-existing file for article "1" was not overwritten by the cleaning step.
    assert json.loads(sentinel_path.read_text())["sentinel"] is True


# `build_knowledge_enrichment_flow` and its tests (test_enrichment_flow_*) were removed
# here (FR-16/AD-18, T-13): context enrichment is deleted entirely — see
# `test_knowledge_flows.py::test_knowledge_flows_module_has_no_enrichment_factory`.


# ---------------------------------------------------------------------------
# Progress reporting (T-10)
# ---------------------------------------------------------------------------


def test_cleaning_flow_reports_step_progress(
    tmp_path: Path, progress_recorder: RecordingProgressReporter
) -> None:
    resolver = LayerResolver(
        layers={"parsed": str(tmp_path / "parsed"), "cleaned": str(tmp_path / "cleaned")},
        sources={"cds": SourceConfig(dir="cds", file="articles.json")},
    )
    parsed_path = resolver.path("parsed", "cds")
    parsed_path.parent.mkdir(parents=True)
    parsed_path.write_text(json.dumps([_parsed_article_payload("1")]), encoding="utf-8")

    config = _base_config(project_root=tmp_path)

    build_knowledge_cleaning_flow(
        config=config, layer_resolver=resolver, source="cds", progress=progress_recorder
    ).run()

    begin_steps = [args for name, args in progress_recorder.calls if name == "begin_step"]
    end_steps = [args for name, args in progress_recorder.calls if name == "end_step"]
    assert len(begin_steps) == 4
    assert len(end_steps) == 4
    assert [args[1] for args in begin_steps] == [1, 2, 3, 4]
    assert all(args[2] == 4 for args in begin_steps)
