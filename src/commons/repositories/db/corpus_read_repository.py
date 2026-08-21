from collections.abc import Sequence

from psycopg import sql

from commons.clients import PostgresClient
from domain.models.retrieval import RetrievedComma

# Shared projection for every method that returns `RetrievedComma`: a comma is never
# returned without its parent article's `source`, `number` and `title` (AD-7; FR-4/FR-9
# need the citation, FR-5 needs the title for the weighted tsvector). `c.id` leads the
# column list (PD-5) so every method unpacks it at the same tuple position. Composed once
# here so `dense_top_k`/`random_top_k`/`text_top_k` cannot drift into different column sets.
_BASE_SELECT = sql.SQL("SELECT c.id, a.source, a.number, a.title, c.comma_number, c.text")

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


def _text_match_query(commas: sql.Identifier, articles: sql.Identifier) -> sql.Composed:
    """Builds the FR-1/FR-2 text-match statement: a union of two single-relation scans.

    AD-13: a predicate whose two branches reference different relations (the former
    `a.tsv_title @@ q OR c.tsv_text @@ q`) is evaluated after the join and never becomes
    an index condition. Matching each relation separately in its own `UNION` branch and
    rejoining the resulting comma ids for projection/scoring keeps both branches
    index-driven (`idx_articles_tsv_title`, `idx_article_commas_tsv_text`). AD-14: ties on
    `ts_rank_cd` are broken by ascending `c.id`, so the cut at `LIMIT` is reproducible.

    Because the two branches name `commas`/`articles` independently, this statement
    cannot reuse an instance's single-`FROM` `_from_clause` (whose aliases only make
    sense inside one `FROM`) — the two `sql.Identifier` values are taken as arguments
    instead.

    Parameterised `%s` twice, in this order: the `to_tsquery` argument, then `LIMIT`.

    The projection column list (`c.id, a.source, a.number, a.title, c.comma_number,
    c.text`) is written out literally rather than concatenated onto `_BASE_SELECT` —
    `_BASE_SELECT`'s `c.`/`a.` aliases belong to a single `FROM`, which this statement's
    two-branch `WITH` does not have. The two lists must be kept in step, or
    `_row_to_comma` silently misreads rows.
    """
    return sql.SQL(
        "WITH q AS (SELECT to_tsquery('italian', %s) AS query), "
        "matched AS ("
        "SELECT c.id FROM {commas} c JOIN {articles} a ON a.id = c.article_id, q "
        "WHERE a.tsv_title @@ q.query "
        "UNION "
        "SELECT c.id FROM {commas} c, q "
        "WHERE c.tsv_text @@ q.query"
        ") "
        "SELECT c.id, a.source, a.number, a.title, c.comma_number, c.text, "
        "ts_rank_cd(a.tsv_title || c.tsv_text, q.query) AS distance "
        "FROM {commas} c "
        "JOIN {articles} a ON a.id = c.article_id "
        "JOIN matched m ON m.id = c.id, q "
        "ORDER BY distance DESC, c.id ASC "
        "LIMIT %s"
    ).format(commas=commas, articles=articles)


class CorpusReadRepository:
    """Read-only repository over `articles` joined to `article_commas` (AD-7).

    Every method joins the two tables through the same `_from_clause`, computed once
    per instance, so a retrieved comma always carries its article's `source`, `number`
    and `title` and no method can silently drop the join. Issues no `INSERT`/`UPDATE`/
    `DELETE`/DDL.

    `extract_lexemes` is the one exception to the join-based shape above: it reads no
    table at all, using Postgres purely as a linguistic engine (PD-5). It lives here,
    not in a class of its own, because it must draw from the same `italian`
    dictionary configuration `_to_tsquery_param`/`_WEIGHTED_TSVECTOR` already use to
    build the GIN-indexed search this class performs (AD-9).
    """

    def __init__(
        self, articles_table: str, article_commas_table: str, client: PostgresClient
    ) -> None:
        """Injects the table names and the `PostgresClient`."""
        self._client = client
        # Kept individually, not just folded into `_from_clause`, because
        # `_text_match_query` needs the two table identifiers on their own — its two
        # `UNION` branches reference `commas`/`articles` independently and cannot share
        # a single `FROM` alias set.
        self._articles = sql.Identifier(articles_table)
        self._article_commas = sql.Identifier(article_commas_table)
        self._from_clause = sql.SQL("{commas} c JOIN {articles} a ON a.id = c.article_id").format(
            commas=self._article_commas,
            articles=self._articles,
        )

    def dense_top_k(self, embedding: list[float], k: int) -> list[RetrievedComma]:
        """Returns the `k` commas closest to `embedding` by cosine distance, ascending.

        Filters `WHERE c.embedding IS NOT NULL` (342 repealed commas carry no vector).
        The `%s::vector` cast is mandatory (`.claude/rules/code-conventions.md`).
        """
        # AD-14: ascending `c.id` breaks ties on equal distance, so the cut at `k` is
        # reproducible instead of left to plan order.
        query = _BASE_SELECT + sql.SQL(
            ", c.embedding <=> %s::vector AS distance FROM {from_clause} "
            "WHERE c.embedding IS NOT NULL ORDER BY distance, c.id LIMIT %s"
        ).format(from_clause=self._from_clause)
        rows = self._client.fetch(query, [embedding, k])
        return [self._row_to_comma(row) for row in rows]

    def random_top_k(self, k: int, seed_key: str) -> list[RetrievedComma]:
        """Returns `k` commas drawn pseudo-randomly, keyed by `seed_key` (FR-3 baseline).

        Restricted to `WHERE c.embedding IS NOT NULL`, the same population `dense_top_k`
        can retrieve — a baseline drawn from a different population is not a control for
        the same thing. `distance` is `nan`: a random draw has no meaningful distance.
        """
        # AD-14: ascending `c.id` breaks ties on the (vanishingly unlikely) `md5` clash,
        # for the same reproducible-cut reason as `dense_top_k` and `text_match_top_k`.
        query = _BASE_SELECT + sql.SQL(
            " FROM {from_clause} WHERE c.embedding IS NOT NULL "
            "ORDER BY md5(c.id::text || %s), c.id LIMIT %s"
        ).format(from_clause=self._from_clause)
        rows = self._client.fetch(query, [seed_key, k])
        return [
            RetrievedComma(
                id=row[0],
                source=row[1],
                article_number=row[2],
                article_title=row[3],
                comma_number=row[4],
                text=row[5],
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

    def comma_count(self) -> int:
        """Returns the total number of rows in `article_commas` (FR-11 corpus state).

        Unlike every other comma-returning method on this class, this counts the
        whole table: no `WHERE c.embedding IS NOT NULL` filter and no join to
        `articles`. FR-11 records the size of the corpus, not the size of the
        retrievable subset.
        """
        query = sql.SQL("SELECT count(*) FROM {commas}").format(commas=self._article_commas)
        rows = self._client.fetch(query)
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

    def extract_lexemes(self, text: str) -> list[str]:
        """Extracts the lexemes `text` yields under the `italian` `to_tsquery` dictionary.

        Args:
            text: Free-form text to extract lexemes from (FR-4). May be empty or
                consist only of stop words.

        Returns:
            The distinct lexemes `to_tsvector('italian', text)` produces, sorted for
            determinism. Raw, not quoted for `to_tsquery` — quoting (PD-6) is the
            caller's job, so a consumer of this method is not handed a pre-escaped
            list it did not ask for. An empty or stop-word-only `text` yields `[]`
            and raises nothing.

        The `italian` configuration is fixed (spec Constraints): stop-word removal
        and stemming come from the same dictionary the GIN indexes this class
        searches are built with (AD-9), which is why extraction lives here and not
        in Python. This method issues no LLM call (FR-4). Uniquely on this class, it
        reads no table: Postgres is used as a linguistic engine, not as a store, so
        there is no join to `articles` and no `embedding IS NOT NULL` filter here.
        """
        query = sql.SQL("SELECT lexeme FROM unnest(to_tsvector('italian', %s)) ORDER BY lexeme")
        rows = self._client.fetch(query, [text])
        return [row[0] for row in rows]

    def text_match_top_k(self, lexemes: list[str], k: int) -> list[RetrievedComma]:
        """Returns the `k` commas matching `lexemes`, ranked by `ts_rank_cd`, descending.

        Args:
            lexemes: Already-normalised lexemes; this method does not tokenise, it only
                OR-joins them into a `to_tsquery` argument.
            k: Maximum number of commas to return.

        Returns:
            Commas whose article title or own text matches the query, most relevant
            first. A comma whose parent article title matches is eligible even when its
            own text does not. Ties on `ts_rank_cd` are broken by ascending
            `article_commas.id` (AD-14), so the cut at `k` is reproducible across query
            plans that return the same match set. Returns an empty list when nothing
            matches — no exception is raised. `distance` here holds the raw `ts_rank_cd`
            score (higher is more relevant), not a cosine distance — the field is reused
            across every text metric rather than adding a second DTO shape.

        Unlike `text_top_k`, this method matches via `_text_match_query` — a union of
        two single-relation branches (AD-13) — rather than returning every comma with
        `0.0` padding. That shape is what makes `idx_articles_tsv_title` and
        `idx_article_commas_tsv_text` usable, and is the only difference from
        `text_top_k`, which the spec 0007 harness still relies on unmodified.
        """
        query = _text_match_query(self._article_commas, self._articles)
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
        """Maps a `(id, source, number, title, comma_number, text, distance)` row."""
        comma_id, source, number, title, comma_number, text, distance = row
        return RetrievedComma(
            id=comma_id,
            source=source,
            article_number=number,
            article_title=title,
            comma_number=comma_number,
            text=text,
            distance=distance,
        )
