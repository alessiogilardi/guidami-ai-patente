from pathlib import Path

from guidami_ai_patente_ingestor.configs import SourceConfig


class LayerResolver:
    """Risolve il path di un artefatto dato il layer e la source.

    Costruito dall'entry point da `IngestorConfig.layers` e
    `IngestorConfig.sources`; iniettato nei builder delle pipeline.
    """

    def __init__(self, layers: dict[str, str], sources: dict[str, SourceConfig]) -> None:
        """Memorizza la mappa layer→dir e source→{dir, file}."""
        self._layers = layers
        self._sources = sources

    def path(self, layer: str, source: str) -> Path:
        """Restituisce `layers[layer] / sources[source].dir / sources[source].file`.

        Raises:
            KeyError: se `layer` o `source` non sono configurati.
        """
        if layer not in self._layers:
            raise KeyError(f"Unknown layer: {layer!r}. Available: {list(self._layers)}")
        if source not in self._sources:
            raise KeyError(f"Unknown source: {source!r}. Available: {list(self._sources)}")
        src = self._sources[source]
        return Path(self._layers[layer]) / src.dir / src.file
