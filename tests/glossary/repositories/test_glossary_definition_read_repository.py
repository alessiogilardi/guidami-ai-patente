from glossary.repositories.glossary_definition_read_repository import (
    GlossaryDefinitionReadRepository,
)


class _FakeClient:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.queries: list[str] = []

    def fetch(self, query, params=None):  # noqa: ANN001
        self.queries.append(str(query))
        return self.rows


def test_it_selects_only_rows_missing_a_simplification() -> None:
    client = _FakeClient([(1, "carreggiata", "def")])
    repository = GlossaryDefinitionReadRepository("glossary_entries", client)

    rows = repository.find_missing_simplifications(force=False)

    assert rows == [type(rows[0])(id=1, term="carreggiata", definition="def")]
    assert "definition_plain IS NULL" in client.queries[0]


def test_force_selects_every_row_regardless_of_definition_plain() -> None:
    client = _FakeClient([(1, "carreggiata", "def"), (2, "banchina", "def2")])
    repository = GlossaryDefinitionReadRepository("glossary_entries", client)

    rows = repository.find_missing_simplifications(force=True)

    assert len(rows) == 2
    assert "definition_plain IS NULL" not in client.queries[0]
