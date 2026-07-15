from guidami_ai_patente_ingestor.configs import IngestorConfig, PipelineLayerConfig
from guidami_ai_patente_ingestor.services import LayerResolver

from ...models.status import CommandReadiness, ReadinessState, SourceReadiness


class StatusInspector:
    """Derives per-(command, entity) executability from the filesystem only.

    No DB, no network: `prepare`/`index` readiness is computed from `Path.exists()`
    on the layers resolved by `LayerResolver`. `reset` has no source dimension and
    no filesystem signal of its own (its cost is only knowable online, see
    `TableHealthChecker`), so it is always reported `RUNNABLE` offline.
    """

    def __init__(self, config: IngestorConfig, layer_resolver: LayerResolver) -> None:
        """Injects the config (source catalogs) and the layer resolver (path lookup)."""
        self._config = config
        self._layer_resolver = layer_resolver

    def evaluate_readiness(self) -> list[CommandReadiness]:
        """Returns one `CommandReadiness` per (command, entity) pair."""
        return [
            self._prepare_readiness("knowledge", self._config.knowledge_preparation),
            self._prepare_readiness("quiz", self._config.quiz_preparation),
            self._index_readiness("knowledge", self._config.knowledge_indexing),
            self._index_readiness("quiz", self._config.quiz_indexing),
            self._reset_readiness("knowledge"),
            self._reset_readiness("quiz"),
        ]

    def _prepare_readiness(
        self, entity: str, layer_config: PipelineLayerConfig
    ) -> CommandReadiness:
        sources = [
            SourceReadiness(source=source, state=self._prepare_state(layer_config, source))
            for source in layer_config.sources
        ]
        return CommandReadiness(command="prepare", entity=entity, sources=sources)

    def _prepare_state(self, layer_config: PipelineLayerConfig, source: str) -> ReadinessState:
        if layer_config.output_layer is None:
            raise ValueError("preparation layer config has no output_layer configured")
        if self._layer_resolver.path(layer_config.output_layer, source).exists():
            return ReadinessState.SKIP
        if not self._layer_resolver.path(layer_config.input_layer, source).exists():
            return ReadinessState.BLOCKED
        return ReadinessState.RUNNABLE

    def _index_readiness(self, entity: str, layer_config: PipelineLayerConfig) -> CommandReadiness:
        sources = [
            SourceReadiness(source=source, state=self._index_state(layer_config, source))
            for source in layer_config.sources
        ]
        return CommandReadiness(command="index", entity=entity, sources=sources)

    def _index_state(self, layer_config: PipelineLayerConfig, source: str) -> ReadinessState:
        if not self._layer_resolver.path(layer_config.input_layer, source).exists():
            return ReadinessState.BLOCKED
        return ReadinessState.RUNNABLE

    def _reset_readiness(self, entity: str) -> CommandReadiness:
        """`reset` has no source dimension: a single synthetic entry per entity."""
        return CommandReadiness(
            command="reset",
            entity=entity,
            sources=[SourceReadiness(source=entity, state=ReadinessState.RUNNABLE)],
        )
