from guidami_ai_patente_ingestor.configs import IngestorConfig, PipelineLayerConfig
from guidami_ai_patente_ingestor.services import LayerResolver

from ...models.status import CommandReadiness, ReadinessState, SourceReadiness


class StatusInspector:
    """Derives per-(command, entity) executability from the filesystem only.

    No DB, no network: `prepare`/`index` readiness is computed from `Path.exists()`
    on the layers resolved by `LayerResolver`. `reset` has no source dimension and
    no filesystem signal of its own (its cost is only knowable online, see
    `TableHealthChecker`), so it is always reported `RUNNABLE` offline.

    Knowledge's `cleaned`/`enriched` layers are per-element directories (see
    `docs/plans/2026-07-17--per-element-knowledge-layers.md`): a directory can be
    partially populated, so there is no honest binary "already done" signal for it.
    `per_element` is passed in by the caller (never inferred from the entity name),
    so this class stays free of hardcoded domain strings.
    """

    def __init__(self, config: IngestorConfig, layer_resolver: LayerResolver) -> None:
        """Injects the config (source catalogs) and the layer resolver (path lookup)."""
        self._config = config
        self._layer_resolver = layer_resolver

    def evaluate_readiness(self) -> list[CommandReadiness]:
        """Returns one `CommandReadiness` per (command, entity) pair."""
        return [
            self._prepare_readiness("knowledge", self._config.knowledge_preparation, True),
            self._prepare_readiness("quiz", self._config.quiz_preparation, False),
            self._index_readiness("knowledge", self._config.knowledge_indexing, True),
            self._index_readiness("quiz", self._config.quiz_indexing, False),
            self._reset_readiness("knowledge"),
            self._reset_readiness("quiz"),
        ]

    def _prepare_readiness(
        self, entity: str, layer_config: PipelineLayerConfig, per_element: bool
    ) -> CommandReadiness:
        sources = [
            SourceReadiness(
                source=source, state=self._prepare_state(layer_config, source, per_element)
            )
            for source in layer_config.sources
        ]
        return CommandReadiness(command="prepare", entity=entity, sources=sources)

    def _prepare_state(
        self, layer_config: PipelineLayerConfig, source: str, per_element: bool
    ) -> ReadinessState:
        if layer_config.output_layer is None:
            raise ValueError("preparation layer config has no output_layer configured")
        # Per-element layers have no honest binary "already done" signal: never SKIP.
        if (
            not per_element
            and self._layer_resolver.path(layer_config.output_layer, source).exists()
        ):
            return ReadinessState.SKIP
        # The input is still a single file, even for knowledge (Decision 19).
        if not self._layer_resolver.path(layer_config.input_layer, source).exists():
            return ReadinessState.BLOCKED
        return ReadinessState.RUNNABLE

    def _index_readiness(
        self, entity: str, layer_config: PipelineLayerConfig, per_element: bool
    ) -> CommandReadiness:
        sources = [
            SourceReadiness(
                source=source, state=self._index_state(layer_config, source, per_element)
            )
            for source in layer_config.sources
        ]
        return CommandReadiness(command="index", entity=entity, sources=sources)

    def _index_state(
        self, layer_config: PipelineLayerConfig, source: str, per_element: bool
    ) -> ReadinessState:
        # Per-element input is a directory: no honest file signal, always runnable.
        if (
            not per_element
            and not self._layer_resolver.path(layer_config.input_layer, source).exists()
        ):
            return ReadinessState.BLOCKED
        return ReadinessState.RUNNABLE

    def _reset_readiness(self, entity: str) -> CommandReadiness:
        """`reset` has no source dimension: a single synthetic entry per entity."""
        return CommandReadiness(
            command="reset",
            entity=entity,
            sources=[SourceReadiness(source=entity, state=ReadinessState.RUNNABLE)],
        )
