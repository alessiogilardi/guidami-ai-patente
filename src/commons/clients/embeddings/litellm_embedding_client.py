from typing import Any

import litellm

from commons.configs import EmbeddingConfig

from .embedding_client import EmbeddingClient


class LiteLLMEmbeddingClient(EmbeddingClient):
    """Embedder cloud via litellm.

    Instrada su OpenRouter (o altro provider) con la sola stringa modello.
    L'API key (OPENROUTER_API_KEY) è letta da litellm dall'ambiente.
    """

    def __init__(self, config: EmbeddingConfig) -> None:
        """Memorizza la configurazione dell'embedder."""
        self._config = config

    def embed_query(self, text: str) -> list[float]:
        """Calcola l'embedding di una query utente."""
        return self._embed([text])[0]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Calcola gli embedding di un batch di passaggi (chunk del corpus)."""
        return self._embed(texts)

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        """Chiama litellm e restituisce i vettori allineati all'ordine di input."""
        kwargs: dict[str, Any] = {
            "model": self._config.model_name,
            "input": inputs,
            "timeout": self._config.timeout,
            "num_retries": self._config.num_retries,
        }
        if self._config.dimensions is not None:
            kwargs["dimensions"] = self._config.dimensions
        response = litellm.embedding(**kwargs)
        ordered = sorted(response.data, key=lambda item: item["index"])
        return [item["embedding"] for item in ordered]
