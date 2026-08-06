from collections.abc import Sequence

from psycopg import sql

from commons.clients import PostgresClient
from domain.models.retrieval import RetrievedComma

# Shared projection for every method that returns `RetrievedComma`: a comma is never
# returned without its parent article's `source`, `number` and `title` (AD-7; FR-4/FR-9
# need the citation, FR-5 needs the title for the weighted tsvector). Composed once here
# so `dense_top_k`/`random_top_k`/`text_top_k` cannot drift into different column sets.
_BASE_SELECT = sql.SQL("SELECT a.source, a.number, a.title, c.comma_number, c.text")

# Weighted tsvector: article title in band A, comma text in band B (FR-5). Title-only
# and text-only variants isolate each field's contribution for the per-field adherence
# report. Reused verbatim by `best_text_rank` and `text_top_k` so the coverage and
# adherence metrics never diverge on the definition.
_WEIGHTED_TSVECTOR = sql.SQL(
    "(setweight(to_tsvector('italian', a.title), 'A') || "
    "setweight(to_tsvector('italian', c.text), 'B'))"
)


def _to_tsquery_param(lexemes: Sequence[str]) -> str:
    """OR-joins `lexemes` into a `to_tsquery` argument (AD-3: OR, never AND)."""
    return " | ".join(lexemes)


class CorpusReadRepository:
    """Read-only repository over `articles` joined to `article_commas` (AD-7).

    Every method joins the two tables through the same `_from_clause`, computed once
    per instance, so a retrieved comma always carries its article's `source`, `number`
    and `title` and no method can silently drop the join. Issues no `INSERT`/`UPDATE`/
    `DELETE`/DDL.
    """

    def __init__(
        self, articles_table: str, article_commas_table: str, client: PostgresClient
    ) -> None:
        """Injects the table names and the `PostgresClient`."""
        self._client = client
        self._from_clause = sql.SQL("{commas} c JOIN {articles} a ON a.id = c.article_id").format(
            commas=sql.Identifier(article_commas_table),
            articles=sql.Identifier(articles_table),
        )

    def dense_top_k(self, embedding: list[float], k: int) -> list[RetrievedComma]:
        """Returns the `k` commas closest to `embedding` by cosine distance, ascending.

        Filters `WHERE c.embedding IS NOT NULL` (342 repealed commas carry no vector).
        The `%s::vector` cast is mandatory (`.claude/rules/code-conventions.md`).
        """
        query = _BASE_SELECT + sql.SQL(
            ", c.embedding <=> %s::vector AS distance FROM {from_clause} "
            "WHERE c.embedding IS NOT NULL ORDER BY distance LIMIT %s"
        ).format(from_clause=self._from_clause)
        rows = self._client.fetch(query, [embedding, k])
        return [self._row_to_comma(row) for row in rows]

    def random_top_k(self, k: int, seed_key: str) -> list[RetrievedComma]:
        """Returns `k` commas drawn pseudo-randomly, keyed by `seed_key` (FR-3 baseline).

        Restricted to `WHERE c.embedding IS NOT NULL`, the same population `dense_top_k`
        can retrieve — a baseline drawn from a different population is not a control for
        the same thing. `distance` is `nan`: a random draw has no meaningful distance.
        """
        query = _BASE_SELECT + sql.SQL(
            " FROM {from_clause} WHERE c.embedding IS NOT NULL "
            "ORDER BY md5(c.id::text || %s) LIMIT %s"
        ).format(from_clause=self._from_clause)
        rows = self._client.fetch(query, [seed_key, k])
        return [
            RetrievedComma(
                source=row[0],
                article_number=row[1],
                article_title=row[2],
                comma_number=row[3],
                text=row[4],
                distance=float("nan"),
            )
            for row in rows
        ]

    def best_text_rank(self, lexemes: list[str]) -> float:
        """Returns the best weighted `ts_rank` any comma in the whole corpus achieves.

        `lexemes` must already be normalised; this method does not tokenise, it only
        OR-joins them into a `to_tsquery` argument. Returns `0.0` on no match. Scans the
        whole corpus (no `embedding IS NOT NULL` filter): this is a text-coverage
        measure, independent of what dense retrieval can find.
        """
        query = sql.SQL(
            "SELECT COALESCE(MAX(ts_rank({weighted}, to_tsquery('italian', %s))), 0.0) "
            "FROM {from_clause}"
        ).format(weighted=_WEIGHTED_TSVECTOR, from_clause=self._from_clause)
        rows = self._client.fetch(query, [_to_tsquery_param(lexemes)])
        return float(rows[0][0])

    def keyword_document_frequency(self, keyword: str) -> int:
        """Counts retrievable commas whose article title + comma text contain `keyword`.

        The `a.title || ' ' || c.text` haystack mirrors
        `cli/services/evaluation/keyword_matching.corpus_haystack` exactly: FR-2 requires
        the coverage test and the ranking hit test to search identical fields.
        """
        query = sql.SQL(
            "SELECT count(*) FROM {from_clause} "
            "WHERE c.embedding IS NOT NULL AND (a.title || ' ' || c.text) ILIKE %s"
        ).format(from_clause=self._from_clause)
        rows = self._client.fetch(query, [f"%{keyword}%"])
        return int(rows[0][0])

    def text_top_k(self, lexemes: list[str], k: int) -> list[RetrievedComma]:
        """Returns the `k` commas with the highest weighted `ts_rank`, descending.

        Same weighted tsvector as `best_text_rank`. `distance` here holds the raw
        `ts_rank` score (higher is more relevant), not a cosine distance — the field is
        reused across both metrics rather than adding a second DTO shape.
        """
        query = _BASE_SELECT + sql.SQL(
            ", ts_rank({weighted}, to_tsquery('italian', %s)) AS distance "
            "FROM {from_clause} ORDER BY distance DESC LIMIT %s"
        ).format(weighted=_WEIGHTED_TSVECTOR, from_clause=self._from_clause)
        rows = self._client.fetch(query, [_to_tsquery_param(lexemes), k])
        return [self._row_to_comma(row) for row in rows]

    def rank_text(
        self, lexemes: list[str], article_title: str, text: str
    ) -> tuple[float, float, float]:
        """Returns `(weighted, title_only, text_only)` `ts_rank` for caller-supplied text.

        Computes over `article_title`/`text` values the caller already has (e.g. an
        already-retrieved `RetrievedComma`'s own fields), not a database lookup by id —
        `RetrievedComma` carries no internal comma id to look up. Uses the exact same
        tsvector weighting as `best_text_rank`/`text_top_k` (title band A, text band B),
        so FR-5's per-field adherence score never diverges from the coverage definition.
        """
        tsquery_param = _to_tsquery_param(lexemes)
        query = sql.SQL(
            "SELECT "
            "ts_rank(setweight(to_tsvector('italian', %s), 'A') || "
            "setweight(to_tsvector('italian', %s), 'B'), to_tsquery('italian', %s)), "
            "ts_rank(setweight(to_tsvector('italian', %s), 'A'), to_tsquery('italian', %s)), "
            "ts_rank(setweight(to_tsvector('italian', %s), 'B'), to_tsquery('italian', %s))"
        )
        rows = self._client.fetch(
            query,
            [
                article_title,
                text,
                tsquery_param,
                article_title,
                tsquery_param,
                text,
                tsquery_param,
            ],
        )
        weighted, title_only, text_only = rows[0]
        return float(weighted), float(title_only), float(text_only)

    @staticmethod
    def _row_to_comma(row: tuple) -> RetrievedComma:
        """Maps a `(source, number, title, comma_number, text, distance)` row."""
        source, number, title, comma_number, text, distance = row
        return RetrievedComma(
            source=source,
            article_number=number,
            article_title=title,
            comma_number=comma_number,
            text=text,
            distance=distance,
        )
