from commons.ai.embedding.configs import EmbeddingClientConfig

from .embedding_client import EmbeddingClient


class SentenceTransformerEmbeddingClient(EmbeddingClient):
    """Local embedder via sentence-transformers.

    Default: no prefix (compatible with bge-m3). Pass `query_prefix`
    and `passage_prefix` for asymmetric models like intfloat/multilingual-e5-*.
    """

    def __init__(
        self,
        config: EmbeddingClientConfig,
        query_prefix: str = "",
        passage_prefix: str = "",
    ) -> None:
        """Loads the sentence-transformers model specified in config."""
        from sentence_transformers import SentenceTransformer

        self._config = config
        self._query_prefix = query_prefix
        self._passage_prefix = passage_prefix
        self._model = SentenceTransformer(config.model_name)

    def embed_query(self, text: str) -> list[float]:
        """Computes the embedding of a user query."""
        vector = self._model.encode(f"{self._query_prefix}{text}", normalize_embeddings=True)
        return vector.tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Computes the embeddings of a batch of passages (corpus chunks)."""
        prefixed = [f"{self._passage_prefix}{text}" for text in texts]
        vectors = self._model.encode(prefixed, normalize_embeddings=True)
        return vectors.tolist()
