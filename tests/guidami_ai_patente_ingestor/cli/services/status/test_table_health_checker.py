from unittest.mock import MagicMock

from guidami_ai_patente_ingestor.cli.models.status import TableHealth
from guidami_ai_patente_ingestor.cli.services.status import TableHealthChecker


def test_assembles_table_health_from_repos() -> None:
    """Existing table reports its row count; absent table skips the count (row_count=None)."""
    present_repo = MagicMock()
    present_repo.table_exists.return_value = True
    present_repo.row_count.return_value = 42

    absent_repo = MagicMock()
    absent_repo.table_exists.return_value = False

    checker = TableHealthChecker(
        {
            "knowledge_chunks": present_repo,
            "quiz_questions": absent_repo,
        }
    )

    tables = checker.check()

    tables_by_name = {t.table: t for t in tables}
    assert tables_by_name["knowledge_chunks"] == TableHealth(
        table="knowledge_chunks", exists=True, row_count=42
    )
    assert tables_by_name["quiz_questions"] == TableHealth(
        table="quiz_questions", exists=False, row_count=None
    )
    absent_repo.row_count.assert_not_called()
