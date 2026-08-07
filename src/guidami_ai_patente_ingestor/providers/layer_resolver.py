from pathlib import Path

from guidami_ai_patente_ingestor.configs import SourceConfig


class LayerResolverProvider:
    """Resolves the path of an artifact given the layer and the source.

    Built by the entry point from `IngestorConfig.layers` and
    `IngestorConfig.sources`; injected into the pipeline builders.
    """

    def __init__(self, layers: dict[str, str], sources: dict[str, SourceConfig]) -> None:
        """Stores the layer→dir and source→{dir, file} maps."""
        self._layers = layers
        self._sources = sources

    def path(self, layer: str, source: str) -> Path:
        """Returns `layers[layer] / sources[source].dir / sources[source].file`.

        Raises:
            KeyError: if `layer` or `source` are not configured.
        """
        if layer not in self._layers:
            raise KeyError(f"Unknown layer: {layer!r}. Available: {list(self._layers)}")
        if source not in self._sources:
            raise KeyError(f"Unknown source: {source!r}. Available: {list(self._sources)}")
        src = self._sources[source]
        return Path(self._layers[layer]) / src.dir / src.file

    def dir(self, layer: str, source: str) -> Path:
        """Return the container directory for a (layer, source) pair.

        Unlike `path()`, it stops before `SourceConfig.file`: per-element layers
        hold one file per element inside this directory.

        Raises:
            KeyError: If `layer` or `source` are not configured.
        """
        if layer not in self._layers:
            raise KeyError(f"Unknown layer: {layer!r}. Available: {list(self._layers)}")
        if source not in self._sources:
            raise KeyError(f"Unknown source: {source!r}. Available: {list(self._sources)}")
        return Path(self._layers[layer]) / self._sources[source].dir
