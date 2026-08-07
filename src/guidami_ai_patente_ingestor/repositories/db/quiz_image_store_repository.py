from commons.clients import PostgresClient
from domain.entities.quiz import QuizImageEntity

from ._upsert_store_repository import UpsertStoreRepository

_QUIZ_IMAGE_TABLE_COLUMNS = ("filename", "description")
_QUIZ_IMAGE_CONFLICT_COLUMNS = ("filename",)


class QuizImageStoreRepository(UpsertStoreRepository[QuizImageEntity]):
    """Writes to `quiz_images` via upsert on `filename`."""

    def __init__(self, table_name: str, client: PostgresClient) -> None:
        """Injects the table name and the `PostgresClient`."""
        super().__init__(
            table_name=table_name,
            columns=_QUIZ_IMAGE_TABLE_COLUMNS,
            conflict_columns=_QUIZ_IMAGE_CONFLICT_COLUMNS,
            client=client,
        )

    @staticmethod
    def _to_db_row(item: QuizImageEntity) -> tuple[object, ...]:
        return (item.filename, item.description)
