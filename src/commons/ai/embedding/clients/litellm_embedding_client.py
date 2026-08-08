import logging
from typing import Any

from commons.ai.embedding.configs import EmbeddingClientConfig

from .embedding_client import EmbeddingClient


class LiteLLMEmbeddingClient(EmbeddingClient):
    """Cloud embedder via litellm.

    Routes to OpenRouter (or another provider) using only the model string.
    The API key (OPENROUTER_API_KEY) is read by litellm from the environment.
    """

    def __init__(self, config: EmbeddingClientConfig) -> None:
        """Stores the embedder configuration."""
        self._config = config

    def embed_query(self, text: str) -> list[float]:
        """Computes the embedding of a user query."""
        return self._embed([text])[0]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Computes the embeddings of a batch of passages (corpus chunks)."""
        return self._embed(texts)

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        """Calls litellm and returns the vectors aligned to the input order."""
        import litellm

        # litellm's own module-level _suppress_loggers() (runs once, on the first import
        # above, in this process) force-sets the "httpx" logger to WARNING, silently
        # overriding whatever level the host process configured (e.g.
        # cli/logging_setup.py's INFO root) — this is the only import site of litellm in
        # the codebase, so undoing that side effect here, right after the import that
        # causes it, is the only place it can be caught.
        logging.getLogger("httpx").setLevel(logging.NOTSET)

        kwargs = self._build_embed_args(inputs)
        response = litellm.embedding(**kwargs)
        ordered = sorted(response.data, key=lambda item: item["index"])
        return [[float(v) for v in item["embedding"]] for item in ordered]

    def _build_embed_args(self, inputs: list[str]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._config.model_name,
            "input": inputs,
            "timeout": self._config.timeout,
            "num_retries": self._config.num_retries,
        }
        if self._config.dimensions is not None:
            kwargs["dimensions"] = self._config.dimensions

        return kwargs
