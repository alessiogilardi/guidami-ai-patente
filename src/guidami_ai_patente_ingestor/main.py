import os

from commons.configs import VectorStoreConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.knowledge_indexing import IndexingPipelineBuilder


def main() -> None:
    """Esegue la pipeline di indicizzazione (full reload di `knowledge_chunks`)."""
    config = IngestorConfig(
        vector_store=VectorStoreConfig(database_url=os.environ["DATABASE_URL"])
    )
    pipeline = IndexingPipelineBuilder(config).build()
    pipeline.run()
