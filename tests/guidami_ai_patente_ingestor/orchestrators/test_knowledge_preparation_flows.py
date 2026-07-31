"""Tests for build_knowledge_cleaning_flow / build_knowledge_enrichment_flow.

Per-element layers (`cleaned`/`enriched`): the flows now rewire through
`LoadJsonDirStep`/`FilterAlreadyDoneStep`/`WriteJsonDirStep` (see
`docs/plans/2026-07-17--per-element-knowledge-layers.md`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from flowstep import Flow, FlowValidator
from flowstep.steps import ApplyStep, AsyncApplyStep
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.configs import PostgresConnectionConfig
from commons.utils import element_id
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
    ArticleContextualizerResponse,
)
from guidami_ai_patente_ingestor.configs import IngestorConfig, PipelineLayerConfig, SourceConfig
from guidami_ai_patente_ingestor.orchestrators import (
    build_knowledge_cleaning_flow,
    build_knowledge_enrichment_flow,
)
from guidami_ai_patente_ingestor.orchestrators.steps.generic import (
    FilterAlreadyDoneStep,
    LoadJsonDirStep,
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
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
        **overrides,  # type: ignore[arg-type]
    )


def _make_layer_resolver() -> LayerResolver:
    return MagicMock(spec=LayerResolver)


def _parsed_article_payload(number: str) -> dict:
    return {
        "number": number,
        "title": f"Articolo {number}",
        "text": f"Testo {number}.",
        "paragraphs": [f"Comma 1 art {number}."],
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


# ---------------------------------------------------------------------------
# build_knowledge_enrichment_flow
# ---------------------------------------------------------------------------


_PROVIDER = OpenRouterProvider(api_key="test-key")


def _patched_agent() -> MagicMock:
    return MagicMock(spec=ArticleContextualizerAgent)


def test_enrichment_flow_returns_flow_instance() -> None:
    with patch.object(ArticleContextualizerAgent, "from_yaml", return_value=_patched_agent()):
        flow = build_knowledge_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="cds",
            open_router_provider=_PROVIDER,
        )
    assert isinstance(flow, Flow)


def test_enrichment_flow_required_input_keys_is_empty_set() -> None:
    with patch.object(ArticleContextualizerAgent, "from_yaml", return_value=_patched_agent()):
        flow = build_knowledge_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="cds",
            open_router_provider=_PROVIDER,
        )
    report = FlowValidator().validate(flow)
    assert report.required_input_keys == set()


def test_enrichment_flow_build_with_validate_true_does_not_raise() -> None:
    with patch.object(ArticleContextualizerAgent, "from_yaml", return_value=_patched_agent()):
        flow = build_knowledge_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="cds",
            open_router_provider=_PROVIDER,
            validate=True,
        )
    assert isinstance(flow, Flow)


def test_enrichment_flow_unknown_source_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        build_knowledge_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="quiz",
            open_router_provider=_PROVIDER,
        )


def test_enrichment_flow_has_five_steps_load_filter_map_enrich_write() -> None:
    with patch.object(ArticleContextualizerAgent, "from_yaml", return_value=_patched_agent()):
        flow = build_knowledge_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="cds",
            open_router_provider=_PROVIDER,
        )

    steps = flow.get_steps()
    assert len(steps) == 5
    assert isinstance(steps[0], LoadJsonDirStep)
    assert isinstance(steps[1], FilterAlreadyDoneStep)
    assert isinstance(steps[2], ApplyStep)
    assert isinstance(steps[3], AsyncApplyStep)
    assert isinstance(steps[4], WriteJsonDirStep)


def test_enrichment_flow_force_false_skips_already_enriched_article_without_calling_agent(
    tmp_path: Path,
) -> None:
    """Decision 18: the filter runs BEFORE the LLM call, so it's what saves the cost."""
    resolver = LayerResolver(
        layers={"cleaned": str(tmp_path / "cleaned"), "enriched": str(tmp_path / "enriched")},
        sources={"cds": SourceConfig(dir="cds", file="articles.json")},
    )
    cleaned_dir = resolver.dir("cleaned", "cds")
    cleaned_dir.mkdir(parents=True)
    for number in ("1", "2"):
        (cleaned_dir / f"{element_id('cds', number)}.json").write_text(
            json.dumps(_cleaned_article_payload(number, "cds")), encoding="utf-8"
        )

    enriched_dir = resolver.dir("enriched", "cds")
    enriched_dir.mkdir(parents=True)
    already_done_id = element_id("cds", "1")
    (enriched_dir / f"{already_done_id}.json").write_text(
        json.dumps({**_cleaned_article_payload("1", "cds"), "contexts": {}}), encoding="utf-8"
    )

    config = _base_config(
        project_root=tmp_path,
        knowledge_preparation=PipelineLayerConfig(
            input_layer="parsed", output_layer="enriched", sources=["cds"]
        ),
    )

    agent = _patched_agent()
    agent.run.return_value = ArticleContextualizerResponse(contexts={0: "Contesto."})

    with patch.object(ArticleContextualizerAgent, "from_yaml", return_value=agent):
        build_knowledge_enrichment_flow(
            config=config,
            layer_resolver=resolver,
            source="cds",
            open_router_provider=_PROVIDER,
            force=False,
        ).run()

    # Only article "2" (not yet enriched) reaches the agent.
    assert agent.run.call_count == 1
    assert sorted(p.stem for p in enriched_dir.glob("*.json")) == sorted(
        [element_id("cds", "1"), element_id("cds", "2")]
    )


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


def test_enrichment_flow_reports_step_and_item_progress(
    tmp_path: Path, progress_recorder: RecordingProgressReporter
) -> None:
    resolver = LayerResolver(
        layers={"cleaned": str(tmp_path / "cleaned"), "enriched": str(tmp_path / "enriched")},
        sources={"cds": SourceConfig(dir="cds", file="articles.json")},
    )
    cleaned_dir = resolver.dir("cleaned", "cds")
    cleaned_dir.mkdir(parents=True)
    (cleaned_dir / f"{element_id('cds', '1')}.json").write_text(
        json.dumps(_cleaned_article_payload("1", "cds")), encoding="utf-8"
    )

    config = _base_config(
        project_root=tmp_path,
        knowledge_preparation=PipelineLayerConfig(
            input_layer="parsed", output_layer="enriched", sources=["cds"]
        ),
    )

    agent = _patched_agent()
    agent.run.return_value = ArticleContextualizerResponse(contexts={0: "Contesto."})

    with patch.object(ArticleContextualizerAgent, "from_yaml", return_value=agent):
        build_knowledge_enrichment_flow(
            config=config,
            layer_resolver=resolver,
            source="cds",
            open_router_provider=_PROVIDER,
            progress=progress_recorder,
        ).run()

    begin_steps = [args for name, args in progress_recorder.calls if name == "begin_step"]
    end_steps = [args for name, args in progress_recorder.calls if name == "end_step"]
    assert len(begin_steps) == 5
    assert len(end_steps) == 5
    assert [args[1] for args in begin_steps] == [1, 2, 3, 4, 5]
    # Proves the reporter reached the injected ContextEnricher, not just the observer.
    assert ("begin_items", ("articles", 1)) in progress_recorder.calls
