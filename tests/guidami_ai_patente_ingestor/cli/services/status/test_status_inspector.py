from pathlib import Path

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.cli.models.status import CommandReadiness, ReadinessState
from guidami_ai_patente_ingestor.cli.services.status import StatusInspector
from guidami_ai_patente_ingestor.configs import IngestorConfig, PipelineLayerConfig, SourceConfig
from guidami_ai_patente_ingestor.services import LayerResolver


def _build_config(tmp_path: Path, **overrides: object) -> IngestorConfig:
    return IngestorConfig(
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
        layers={
            "parsed": str(tmp_path / "parsed"),
            "enriched": str(tmp_path / "enriched"),
        },
        **overrides,  # type: ignore[arg-type]
    )


def _entity_readiness(
    readiness: list[CommandReadiness], command: str, entity: str
) -> CommandReadiness:
    for item in readiness:
        if item.command == command and item.entity == entity:
            return item
    raise AssertionError(f"no CommandReadiness found for command={command!r} entity={entity!r}")


def test_knowledge_prepare_never_skips_even_when_enriched_populated(tmp_path: Path) -> None:
    """Decision 15: per-element layers have no honest SKIP signal for knowledge.

    The output file is written at the exact path `path()` resolves to, so the
    current (unfixed) implementation would report SKIP: this is what must change.
    """
    (tmp_path / "enriched" / "populated_src").mkdir(parents=True)
    (tmp_path / "enriched" / "populated_src" / "f.json").write_text("{}")
    (tmp_path / "parsed" / "populated_src").mkdir(parents=True)
    (tmp_path / "parsed" / "populated_src" / "f.json").write_text("{}")

    config = _build_config(
        tmp_path,
        sources={"populated_src": SourceConfig(dir="populated_src", file="f.json")},
        knowledge_preparation=PipelineLayerConfig(
            input_layer="parsed",
            output_layer="enriched",
            sources=["populated_src"],
        ),
    )
    layer_resolver = LayerResolver(layers=config.layers, sources=config.sources)
    inspector = StatusInspector(config, layer_resolver)

    readiness = inspector.evaluate_readiness()

    prepare_knowledge = _entity_readiness(readiness, "prepare", "knowledge")
    states_by_source = {s.source: s.state for s in prepare_knowledge.sources}
    assert states_by_source["populated_src"] == ReadinessState.RUNNABLE
    assert ReadinessState.SKIP not in states_by_source.values()


def test_knowledge_prepare_blocked_when_parsed_input_missing(tmp_path: Path) -> None:
    """Decision 19: prepare's input is still a single file, so BLOCKED is preserved."""
    config = _build_config(
        tmp_path,
        sources={"missing_src": SourceConfig(dir="missing_src", file="f.json")},
        knowledge_preparation=PipelineLayerConfig(
            input_layer="parsed",
            output_layer="enriched",
            sources=["missing_src"],
        ),
    )
    layer_resolver = LayerResolver(layers=config.layers, sources=config.sources)
    inspector = StatusInspector(config, layer_resolver)

    readiness = inspector.evaluate_readiness()

    prepare_knowledge = _entity_readiness(readiness, "prepare", "knowledge")
    states_by_source = {s.source: s.state for s in prepare_knowledge.sources}
    assert states_by_source["missing_src"] == ReadinessState.BLOCKED


def test_knowledge_index_always_runnable_even_when_enriched_input_missing(tmp_path: Path) -> None:
    """Decision 19: index's input is now a directory, so no BLOCKED signal either."""
    (tmp_path / "enriched" / "cds").mkdir(parents=True)
    (tmp_path / "enriched" / "cds" / "f.json").write_text("{}")
    # cap: enriched input missing.

    config = _build_config(
        tmp_path,
        sources={
            "cds": SourceConfig(dir="cds", file="f.json"),
            "cap": SourceConfig(dir="cap", file="f.json"),
        },
        knowledge_indexing=PipelineLayerConfig(input_layer="enriched", sources=["cds", "cap"]),
    )
    layer_resolver = LayerResolver(layers=config.layers, sources=config.sources)
    inspector = StatusInspector(config, layer_resolver)

    readiness = inspector.evaluate_readiness()

    index_knowledge = _entity_readiness(readiness, "index", "knowledge")
    states_by_source = {s.source: s.state for s in index_knowledge.sources}
    assert states_by_source["cds"] == ReadinessState.RUNNABLE
    assert states_by_source["cap"] == ReadinessState.RUNNABLE
    assert ReadinessState.SKIP not in states_by_source.values()
    assert ReadinessState.BLOCKED not in states_by_source.values()


def test_default_config_reports_reg_readiness_for_prepare_and_index(tmp_path: Path) -> None:
    """FR-4 AC5: with the real (yaml + Python) defaults, `reg` gets prepare/index readiness.

    `layers` omits `cleaned`, mirroring `_build_config`'s existing override, but
    knowledge's prepare/index readiness is `per_element=True` and never dereferences
    that key (see `StatusInspector._prepare_state`/`_index_state`).
    """
    config = _build_config(tmp_path)
    layer_resolver = LayerResolver(layers=config.layers, sources=config.sources)
    inspector = StatusInspector(config, layer_resolver)

    readiness = inspector.evaluate_readiness()

    prepare_knowledge = _entity_readiness(readiness, "prepare", "knowledge")
    index_knowledge = _entity_readiness(readiness, "index", "knowledge")
    assert any(s.source == "reg" for s in prepare_knowledge.sources)
    assert any(s.source == "reg" for s in index_knowledge.sources)


def test_quiz_prepare_still_uses_skip_and_blocked_signals(tmp_path: Path) -> None:
    """Quiz is unaffected by the per-element rework (Decision 15 scopes it to knowledge only)."""
    (tmp_path / "enriched" / "skip_src").mkdir(parents=True)
    (tmp_path / "enriched" / "skip_src" / "f.json").write_text("{}")
    (tmp_path / "parsed" / "run_src").mkdir(parents=True)
    (tmp_path / "parsed" / "run_src" / "f.json").write_text("{}")
    # block_src: neither parsed nor enriched exist.

    config = _build_config(
        tmp_path,
        sources={
            "skip_src": SourceConfig(dir="skip_src", file="f.json"),
            "block_src": SourceConfig(dir="block_src", file="f.json"),
            "run_src": SourceConfig(dir="run_src", file="f.json"),
        },
        quiz_preparation=PipelineLayerConfig(
            input_layer="parsed",
            output_layer="enriched",
            sources=["skip_src", "block_src", "run_src"],
        ),
    )
    layer_resolver = LayerResolver(layers=config.layers, sources=config.sources)
    inspector = StatusInspector(config, layer_resolver)

    readiness = inspector.evaluate_readiness()

    prepare_quiz = _entity_readiness(readiness, "prepare", "quiz")
    states_by_source = {s.source: s.state for s in prepare_quiz.sources}
    assert states_by_source["skip_src"] == ReadinessState.SKIP
    assert states_by_source["block_src"] == ReadinessState.BLOCKED
    assert states_by_source["run_src"] == ReadinessState.RUNNABLE
