from commons.configs import EmbeddingConfig

from .embedding_client import EmbeddingClient


class E5SmallEmbeddingClient(EmbeddingClient):
    """Embedder locale via sentence-transformers (intfloat/multilingual-e5-small).

    Richiede `sentence-transformers` installato (`uv add sentence-transformers`).
    I prefissi e5 `query: ` / `passage: ` sono applicati per default.
    """

    def __init__(
        self,
        config: EmbeddingConfig,
        query_prefix: str = "query: ",
        passage_prefix: str = "passage: ",
    ) -> None:
        """Carica il modello sentence-transformers indicato in config."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers non è installato: `uv add sentence-transformers`"
            ) from exc
        self._config = config
        self._query_prefix = query_prefix
        self._passage_prefix = passage_prefix
        self._model = SentenceTransformer(config.model_name)

    def embed_query(self, text: str) -> list[float]:
        """Calcola l'embedding di una query utente."""
        vector = self._model.encode(f"{self._query_prefix}{text}", normalize_embeddings=True)
        return vector.tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Calcola gli embedding di un batch di passaggi (chunk del corpus)."""
        prefixed = [f"{self._passage_prefix}{text}" for text in texts]
        vectors = self._model.encode(prefixed, normalize_embeddings=True)
        return vectors.tolist()
